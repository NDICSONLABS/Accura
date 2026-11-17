import pytest
from decimal import Decimal
from datetime import date

from app.models.enums import (
    UserRole, PeriodStatus, FiscalYearStatus, EntryStatus,
    GrantStatus, TrancheStatus, BudgetEnforcementMode,
)
from app.models.user import User
from app.models.account import Account
from app.models.master_data import ThirdParty, Fund
from app.models.period import FiscalYear, AccountingPeriod
from app.models.ledger import JournalLine
from app.models.grants import GrantTranche
from app.models.settings import OrganizationSetting
from app.models.currency import Currency
from app.services.grant_service import (
    create_grant, add_tranche, activate_grant, get_grant_weighted_rate,
    create_fund_call, post_fund_call, create_grant_receipt, post_grant_receipt,
    GrantCreateSchema, TrancheCreateSchema, FundCallCreateSchema, GrantReceiptCreateSchema,
)
from app.services.budget_admin_service import (
    create_budget_line, update_budget_line, delete_budget_line, BudgetLineSchema,
)
from app.services.reporting_service import get_trial_balance


@pytest.fixture
def grant_context(db_session):
    settings = db_session.query(OrganizationSetting).first()
    settings.maker_checker_approval_enabled = False
    settings.multi_currency_enabled = True
    settings.donor_fund_tracking_enabled = True
    settings.budget_control_enabled = False
    db_session.commit()

    user = User(email="grant@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)
    db_session.flush()

    fy = FiscalYear(code="2095", start_date=date(2095, 1, 1), end_date=date(2095, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    period = AccountingPeriod(
        fiscal_year_id=fy.id, period_number=1,
        start_date=date(2095, 1, 1), end_date=date(2095, 1, 31), status=PeriodStatus.OPEN,
    )
    db_session.add(period)
    db_session.flush()

    receivable = db_session.query(Account).filter(Account.code == "411").first()
    donor = ThirdParty(name="DONOR TEST AGENCY", account_id=receivable.id)
    db_session.add(donor)
    db_session.flush()

    fund = Fund(code="GRANT-TST-FUND", label="Test Restricted Fund",
                donor_name="Donor Test", currency_code="USD", is_restricted=True)
    db_session.add(fund)
    db_session.flush()

    return {"user": user, "fy": fy, "period": period, "donor": donor, "fund": fund}


def _grant(ctx, code="GRANT-TST-001"):
    return GrantCreateSchema(
        code=code, label="Test Grant",
        donor_third_party_id=ctx["donor"].id,
        fund_id=ctx["fund"].id,
        currency_code="USD",
        total_committed_foreign=Decimal("100000.00"),
        start_date=date(2095, 1, 1), end_date=date(2095, 12, 31),
        fund_account_code="1611", receivable_account_code="411",
    )


def test_fund_call_posts_receivable_and_restricted_fund(db_session, grant_context):
    ctx = grant_context
    grant = create_grant(db_session, ctx["user"].id, _grant(ctx))
    add_tranche(db_session, grant.id, TrancheCreateSchema(
        tranche_number=1, expected_date=date(2095, 1, 5),
        foreign_amount=Decimal("50000.00"), exchange_rate=Decimal("600.000000"),
    ))
    activate_grant(db_session, grant.id)

    tranche = db_session.query(GrantTranche).filter(GrantTranche.grant_id == grant.id).first()

    call = create_fund_call(db_session, ctx["user"].id, FundCallCreateSchema(
        grant_id=grant.id, tranche_id=tranche.id,
        call_date=date(2095, 1, 10), due_date=date(2095, 2, 10),
        reference="FC-001", description="First tranche",
        foreign_amount=Decimal("50000.00"), exchange_rate=Decimal("600.000000"),
    ))
    posted = post_fund_call(db_session, call.id, ctx["user"].id)

    assert posted.status == EntryStatus.POSTED
    assert posted.base_amount == Decimal("30000000")

    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == posted.journal_entry_id).all()
    assert sum(l.base_debit for l in lines) == sum(l.base_credit for l in lines) == Decimal("30000000")

    db_session.refresh(tranche)
    assert tranche.status == TrancheStatus.CALLED

    tb = get_trial_balance(db_session, ctx["fy"].id, date(2095, 1, 31))
    assert sum(r.closing_debit for r in tb) == sum(r.closing_credit for r in tb)


def test_grant_receipt_recognizes_fx_gain(db_session, grant_context):
    ctx = grant_context
    grant = create_grant(db_session, ctx["user"].id, _grant(ctx, "GRANT-TST-002"))
    add_tranche(db_session, grant.id, TrancheCreateSchema(
        tranche_number=1, expected_date=date(2095, 1, 5),
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("600.000000"),
    ))
    activate_grant(db_session, grant.id)
    tranche = db_session.query(GrantTranche).filter(GrantTranche.grant_id == grant.id).first()

    call = create_fund_call(db_session, ctx["user"].id, FundCallCreateSchema(
        grant_id=grant.id, tranche_id=tranche.id,
        call_date=date(2095, 1, 10), due_date=date(2095, 2, 10),
        reference="FC-002", description="Tranche 1",
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("600.000000"),
    ))
    post_fund_call(db_session, call.id, ctx["user"].id)

    receipt = create_grant_receipt(db_session, ctx["user"].id, GrantReceiptCreateSchema(
        fund_call_id=call.id, receipt_date=date(2095, 1, 20),
        journal_code="BQ1", treasury_account_code="521",
        reference="RC-001", description="Cash received",
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("610.000000"),
    ))

    assert receipt.base_amount == Decimal("610000")
    assert receipt.receivable_cleared_base == Decimal("600000")
    assert receipt.fx_gain_loss_base == Decimal("10000")

    posted = post_grant_receipt(db_session, receipt.id, ctx["user"].id)
    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == posted.journal_entry_id).all()

    gain_account = db_session.query(Account).filter(Account.code == "776").first()
    gain_lines = [l for l in lines if l.account_id == gain_account.id]
    assert len(gain_lines) == 1
    assert gain_lines[0].base_credit == Decimal("10000")
    assert sum(l.base_debit for l in lines) == sum(l.base_credit for l in lines)

    db_session.refresh(tranche)
    assert tranche.status == TrancheStatus.RECEIVED


def test_weighted_average_rate(db_session, grant_context):
    ctx = grant_context
    grant = create_grant(db_session, ctx["user"].id, _grant(ctx, "GRANT-TST-003"))

    t1 = add_tranche(db_session, grant.id, TrancheCreateSchema(
        tranche_number=1, expected_date=date(2095, 1, 5),
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("600.000000"),
    ))
    add_tranche(db_session, grant.id, TrancheCreateSchema(
        tranche_number=2, expected_date=date(2095, 6, 5),
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("620.000000"),
    ))
    activate_grant(db_session, grant.id)

    call = create_fund_call(db_session, ctx["user"].id, FundCallCreateSchema(
        grant_id=grant.id, tranche_id=t1.id,
        call_date=date(2095, 1, 10), due_date=date(2095, 2, 10),
        reference="FC-003", description="T1",
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("600.000000"),
    ))
    post_fund_call(db_session, call.id, ctx["user"].id)

    # Only tranche 1 is CALLED -> weighted rate = 600
    assert get_grant_weighted_rate(db_session, grant.id) == Decimal("600.000000")


def test_budget_line_cannot_be_reduced_below_consumption(db_session, grant_context):
    ctx = grant_context
    settings = db_session.query(OrganizationSetting).first()
    settings.budget_control_enabled = True
    settings.budget_enforcement_mode = BudgetEnforcementMode.STRICT
    db_session.commit()

    expense = Account(code="987", label="Budget Guard Expense", account_class=6,
                      normal_balance="DEBIT", is_postable=True)
    bank = db_session.query(Account).filter(Account.code == "521").first()
    db_session.add(expense)
    db_session.flush()

    line = create_budget_line(db_session, BudgetLineSchema(
        account_code=expense.code, fiscal_year_id=ctx["fy"].id,
        approved_amount=Decimal("500000"),
    ))

    from app.services.ledger_service import (
        create_and_validate_entry, post_journal_entry,
        JournalEntryCreateSchema, JournalLineSchema,
    )

    entry = create_and_validate_entry(db_session, ctx["user"].id, JournalEntryCreateSchema(
        journal_code="OD", fiscal_year_code=ctx["fy"].code, period_id=ctx["period"].id,
        entry_date=date(2095, 1, 15), description="Budget consumption",
        lines=[
            JournalLineSchema(account_code=expense.code, base_debit=Decimal("300000"), budget_line_id=line.id),
            JournalLineSchema(account_code=bank.code, base_credit=Decimal("300000")),
        ],
    ))
    post_journal_entry(db_session, entry.id, ctx["user"].id)

    with pytest.raises(ValueError) as excinfo:
        update_budget_line(db_session, line.id, Decimal("200000"))
    assert "cannot be reduced below posted consumption" in str(excinfo.value)

    with pytest.raises(ValueError) as excinfo:
        delete_budget_line(db_session, line.id)
    assert "posted consumption" in str(excinfo.value)

    updated = update_budget_line(db_session, line.id, Decimal("600000"))
    assert updated.approved_amount == Decimal("600000")


def test_strict_budget_blocks_overrun(db_session, grant_context):
    ctx = grant_context
    settings = db_session.query(OrganizationSetting).first()
    settings.budget_control_enabled = True
    settings.budget_enforcement_mode = BudgetEnforcementMode.STRICT
    db_session.commit()

    expense = Account(code="988", label="Overrun Expense", account_class=6,
                      normal_balance="DEBIT", is_postable=True)
    bank = db_session.query(Account).filter(Account.code == "521").first()
    db_session.add(expense)
    db_session.flush()

    line = create_budget_line(db_session, BudgetLineSchema(
        account_code=expense.code, fiscal_year_id=ctx["fy"].id,
        approved_amount=Decimal("100000"),
    ))

    from app.services.ledger_service import (
        create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema,
    )

    with pytest.raises(ValueError) as excinfo:
        create_and_validate_entry(db_session, ctx["user"].id, JournalEntryCreateSchema(
            journal_code="OD", fiscal_year_code=ctx["fy"].code, period_id=ctx["period"].id,
            entry_date=date(2095, 1, 15), description="Overrun attempt",
            lines=[
                JournalLineSchema(account_code=expense.code, base_debit=Decimal("150000"), budget_line_id=line.id),
                JournalLineSchema(account_code=bank.code, base_credit=Decimal("150000")),
            ],
        ))

    assert "Budget exceeded" in str(excinfo.value)

def test_restricted_fund_sub_account_is_postable(db_session, grant_context):
    """1611 must exist, be Class 1, and be postable."""
    account = db_session.query(Account).filter(Account.code == "1611").first()
    assert account is not None, "Account 1611 missing — run migrations."
    assert account.account_class == 1
    assert account.is_postable is True
    assert account.requires_third_party is False


def test_partial_receipt_keeps_tranche_called(db_session, grant_context):
    """A partial receipt must NOT mark the tranche as RECEIVED."""
    ctx = grant_context
    grant = create_grant(db_session, ctx["user"].id, _grant(ctx, "GRANT-TST-004"))
    tranche = add_tranche(db_session, grant.id, TrancheCreateSchema(
        tranche_number=1, expected_date=date(2095, 1, 5),
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("600.000000"),
    ))
    activate_grant(db_session, grant.id)

    call = create_fund_call(db_session, ctx["user"].id, FundCallCreateSchema(
        grant_id=grant.id, tranche_id=tranche.id,
        call_date=date(2095, 1, 10), due_date=date(2095, 2, 10),
        reference="FC-004", description="Tranche 1",
        foreign_amount=Decimal("1000.00"), exchange_rate=Decimal("600.000000"),
    ))
    post_fund_call(db_session, call.id, ctx["user"].id)

    # First half received
    r1 = create_grant_receipt(db_session, ctx["user"].id, GrantReceiptCreateSchema(
        fund_call_id=call.id, receipt_date=date(2095, 1, 20),
        journal_code="BQ1", treasury_account_code="521",
        reference="RC-004A", description="Half 1",
        foreign_amount=Decimal("500.00"), exchange_rate=Decimal("600.000000"),
    ))
    post_grant_receipt(db_session, r1.id, ctx["user"].id)

    db_session.refresh(tranche)
    assert tranche.status == TrancheStatus.CALLED, "Partial receipt must not close the tranche."

    # Second half received
    r2 = create_grant_receipt(db_session, ctx["user"].id, GrantReceiptCreateSchema(
        fund_call_id=call.id, receipt_date=date(2095, 1, 25),
        journal_code="BQ1", treasury_account_code="521",
        reference="RC-004B", description="Half 2",
        foreign_amount=Decimal("500.00"), exchange_rate=Decimal("600.000000"),
    ))
    post_grant_receipt(db_session, r2.id, ctx["user"].id)

    db_session.refresh(tranche)
    assert tranche.status == TrancheStatus.RECEIVED

    tb = get_trial_balance(db_session, ctx["fy"].id, date(2095, 1, 31))
    assert sum(r.closing_debit for r in tb) == sum(r.closing_credit for r in tb)