import pytest
from decimal import Decimal
from datetime import date, datetime, timezone

from app.models.enums import (
    EntryStatus, UserRole, NormalBalance, PeriodStatus, FiscalYearStatus,
)
from app.models.user import User
from app.models.account import Account
from app.models.ledger import JournalLine
from app.models.period import FiscalYear, AccountingPeriod
from app.models.master_data import AccountingJournal
from app.models.currency import Currency
from app.models.settings import OrganizationSetting

from app.services.ledger_service import (
    create_and_validate_entry,
    post_journal_entry,
    reverse_journal_entry,
    list_journal_entries,
    get_journal_entry_detail,
    JournalEntryCreateSchema,
    JournalLineSchema,
    JournalListFilters,
)
from app.services.reporting_service import get_general_ledger, GLFilters, get_trial_balance
from app.services.statements_service import get_compte_de_resultat


@pytest.fixture
def daily_flow_context(db_session):
    settings = db_session.query(OrganizationSetting).first()
    settings.maker_checker_approval_enabled = False
    settings.budget_control_enabled = False
    settings.donor_fund_tracking_enabled = False
    settings.project_cost_center_enabled = False
    db_session.commit()

    preparer = User(email="flow_preparer@test.com", password_hash="hash", role=UserRole.ACCOUNTANT_PREPARER)
    approver = User(email="flow_approver@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add_all([preparer, approver])
    db_session.flush()

    fy = FiscalYear(
        code="2070", start_date=date(2070, 1, 1), end_date=date(2070, 12, 31),
        status=FiscalYearStatus.OPEN,
    )
    db_session.add(fy)
    db_session.flush()

    period = AccountingPeriod(
        fiscal_year_id=fy.id, period_number=1,
        start_date=date(2070, 1, 1), end_date=date(2070, 1, 31),
        status=PeriodStatus.OPEN,
    )
    db_session.add(period)
    db_session.flush()

    journal = AccountingJournal(code="TST8", label="Flow Journal", journal_type="MANUAL")
    db_session.add(journal)
    db_session.flush()

    expense = Account(code="980", label="Flow Expense", account_class=6,
                      normal_balance=NormalBalance.DEBIT, is_postable=True)
    bank = Account(code="981", label="Flow Bank", account_class=5,
                   normal_balance=NormalBalance.DEBIT, is_postable=True)
    db_session.add_all([expense, bank])
    db_session.flush()

    return {
        "preparer": preparer, "approver": approver, "fy": fy,
        "period": period, "journal": journal, "expense": expense, "bank": bank,
    }


def _payload(ctx, amount: Decimal, entry_day: int = 15) -> JournalEntryCreateSchema:
    return JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["period"].id,
        entry_date=date(2070, 1, entry_day),
        description="Daily flow transaction",
        lines=[
            JournalLineSchema(account_code=ctx["expense"].code, base_debit=amount),
            JournalLineSchema(account_code=ctx["bank"].code, base_credit=amount),
        ],
    )


def test_full_daily_transaction_lifecycle(db_session, daily_flow_context):
    ctx = daily_flow_context
    amount = Decimal("150000")

    # 1. CREATE DRAFT
    entry = create_and_validate_entry(db_session, ctx["preparer"].id, _payload(ctx, amount))
    assert entry.status == EntryStatus.DRAFT
    assert entry.voucher_number == "TST8-2070-0001"

    # 2. DETAIL VIEW SHOWS BALANCED LINES
    detail = get_journal_entry_detail(db_session, entry.id)
    assert detail is not None
    assert detail["total_debit"] == amount
    assert detail["total_credit"] == amount
    assert detail["difference"] == Decimal("0")
    assert len(detail["lines"]) == 2

    # 3. DRAFT IS EXCLUDED FROM REPORTS
    gl_before = get_general_ledger(db_session, GLFilters(fiscal_year_id=ctx["fy"].id))
    assert len(gl_before) == 0

    # 4. POST
    posted = post_journal_entry(db_session, entry.id, ctx["approver"].id)
    assert posted.status == EntryStatus.POSTED
    assert posted.posted_at is not None

    # 5. GENERAL LEDGER NOW CONTAINS THE LINES
    gl_after = get_general_ledger(db_session, GLFilters(fiscal_year_id=ctx["fy"].id))
    assert len(gl_after) == 2

    # 6. TRIAL BALANCE IS BALANCED
    tb = get_trial_balance(db_session, ctx["fy"].id, date(2070, 1, 31))
    assert sum(r.movement_debit for r in tb) == sum(r.movement_credit for r in tb)
    assert sum(r.closing_debit for r in tb) == sum(r.closing_credit for r in tb)

    # 7. INCOME STATEMENT REFLECTS THE EXPENSE
    cr = get_compte_de_resultat(db_session, ctx["fy"].id)
    assert cr.total_charges == amount
    assert cr.total_produits == Decimal("0")
    assert cr.resultat == -amount

    # 8. JOURNAL LIST FILTERING BY STATUS
    posted_rows = list_journal_entries(
        db_session, JournalListFilters(fiscal_year_id=ctx["fy"].id, status=EntryStatus.POSTED)
    )
    assert len(posted_rows) == 1

    # 9. SEARCH BY VOUCHER
    search_rows = list_journal_entries(
        db_session, JournalListFilters(search="TST8-2070-0001")
    )
    assert len(search_rows) == 1

    # 10. REVERSAL (CONTRE-PASSATION)
    reversal = reverse_journal_entry(
        db_session, posted.id, ctx["approver"].id, date(2070, 1, 20)
    )
    assert reversal.status == EntryStatus.POSTED
    assert reversal.reference == f"REV-{posted.voucher_number}"
    assert reversal.voucher_number == "TST8-2070-0002"

    # 11. REVERSAL NETS THE EXPENSE TO ZERO
    cr_after = get_compte_de_resultat(db_session, ctx["fy"].id)
    assert cr_after.total_charges == Decimal("0")
    assert cr_after.resultat == Decimal("0")

    # 12. TRIAL BALANCE STILL BALANCED AFTER REVERSAL
    tb_after = get_trial_balance(db_session, ctx["fy"].id, date(2070, 1, 31))
    assert sum(r.closing_debit for r in tb_after) == sum(r.closing_credit for r in tb_after)


def test_entry_date_outside_period_is_rejected(db_session, daily_flow_context):
    ctx = daily_flow_context

    bad = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["period"].id,
        entry_date=date(2070, 3, 15),  # March, but period 1 is January
        description="Out of period",
        lines=[
            JournalLineSchema(account_code=ctx["expense"].code, base_debit=Decimal("1000")),
            JournalLineSchema(account_code=ctx["bank"].code, base_credit=Decimal("1000")),
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        create_and_validate_entry(db_session, ctx["preparer"].id, bad)

    assert "outside the selected accounting period" in str(excinfo.value)


def test_line_cannot_have_both_debit_and_credit(db_session, daily_flow_context):
    ctx = daily_flow_context

    bad = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["period"].id,
        entry_date=date(2070, 1, 15),
        description="Both sides on one line",
        lines=[
            JournalLineSchema(
                account_code=ctx["expense"].code,
                base_debit=Decimal("1000"),
                base_credit=Decimal("1000"),
            ),
        ],
    )

    with pytest.raises(ValueError) as excinfo:
        create_and_validate_entry(db_session, ctx["preparer"].id, bad)

    assert "both a debit and a credit" in str(excinfo.value)