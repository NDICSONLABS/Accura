import pytest
from decimal import Decimal
from datetime import date

from app.models.enums import UserRole, PeriodStatus, FiscalYearStatus, EntryStatus
from app.models.user import User
from app.models.account import Account
from app.models.master_data import ThirdParty
from app.models.period import FiscalYear, AccountingPeriod
from app.models.ledger import JournalLine
from app.models.settings import OrganizationSetting
from app.models.currency import Currency
from app.services.accrual_service import (
    create_supplier_bill, post_supplier_bill, get_bill_totals,
    create_settlement, post_settlement,
    SupplierBillCreateSchema, BillLineSchema,
    SettlementCreateSchema, SettlementAllocationSchema,
)
from app.services.reporting_service import get_trial_balance


@pytest.fixture
def ap_context(db_session):
    settings = db_session.query(OrganizationSetting).first()
    settings.maker_checker_approval_enabled = False
    settings.tax_withholding_enabled = True
    settings.multi_currency_enabled = True
    db_session.commit()

    user = User(email="ap@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)
    db_session.flush()

    fy = FiscalYear(code="2090", start_date=date(2090, 1, 1), end_date=date(2090, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    period = AccountingPeriod(
        fiscal_year_id=fy.id, period_number=1,
        start_date=date(2090, 1, 1), end_date=date(2090, 1, 31), status=PeriodStatus.OPEN,
    )
    db_session.add(period)
    db_session.flush()

    expense = Account(code="985", label="AP Expense", account_class=6, normal_balance="DEBIT", is_postable=True)
    db_session.add(expense)
    db_session.flush()

    supplier_account = db_session.query(Account).filter(Account.code == "401").first()
    supplier = ThirdParty(name="AP SUPPLIER TEST", account_id=supplier_account.id)
    db_session.add(supplier)
    db_session.flush()

    return {"user": user, "fy": fy, "period": period, "expense": expense, "supplier": supplier}


def _bill(ctx, reference, net="1000000", vat="0", deductible=False, wht="0", currency="XAF", rate="1.000000"):
    return SupplierBillCreateSchema(
        third_party_id=ctx["supplier"].id,
        bill_date=date(2090, 1, 10),
        due_date=date(2090, 2, 10),
        reference=reference,
        description="Test bill",
        currency_code=currency,
        exchange_rate=Decimal(rate),
        withholding_tax_base=Decimal(wht),
        vat_account_code="445" if deductible else None,
        lines=[BillLineSchema(
            account_code=ctx["expense"].code,
            base_amount=Decimal(net),
            vat_amount=Decimal(vat),
            vat_deductible=deductible,
        )],
    )


def test_bill_with_wht_posts_balanced(db_session, ap_context):
    ctx = ap_context
    bill = create_supplier_bill(db_session, ctx["user"].id, _bill(ctx, "AP-001", wht="100000"))
    posted = post_supplier_bill(db_session, bill.id, ctx["user"].id)

    assert posted.status == EntryStatus.POSTED

    totals = get_bill_totals(db_session, posted)
    assert totals["net_payable"] == Decimal("900000")
    assert totals["payment_status"] == "UNPAID"

    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == posted.journal_entry_id).all()
    assert sum(l.base_debit for l in lines) == sum(l.base_credit for l in lines) == Decimal("1000000")

    tb = get_trial_balance(db_session, ctx["fy"].id, date(2090, 1, 31))
    assert sum(r.closing_debit for r in tb) == sum(r.closing_credit for r in tb)


def test_non_deductible_vat_is_capitalized(db_session, ap_context):
    ctx = ap_context
    bill = create_supplier_bill(
        db_session, ctx["user"].id,
        _bill(ctx, "AP-002", net="1000000", vat="192500", deductible=False),
    )
    totals = get_bill_totals(db_session, bill)
    assert totals["expense_total"] == Decimal("1192500")
    assert totals["deductible_vat"] == Decimal("0")


def test_partial_settlement_updates_payment_status(db_session, ap_context):
    ctx = ap_context
    bill = create_supplier_bill(db_session, ctx["user"].id, _bill(ctx, "AP-003"))
    post_supplier_bill(db_session, bill.id, ctx["user"].id)

    settlement = create_settlement(db_session, ctx["user"].id, SettlementCreateSchema(
        third_party_id=ctx["supplier"].id,
        settlement_date=date(2090, 1, 20),
        journal_code="BQ1",
        treasury_account_code="521",
        reference="PAY-001",
        description="Partial payment",
        allocations=[SettlementAllocationSchema(bill_id=bill.id, allocated_foreign_amount=Decimal("400000"))],
    ))
    post_settlement(db_session, settlement.id, ctx["user"].id)

    totals = get_bill_totals(db_session, bill)
    assert totals["paid"] == Decimal("400000")
    assert totals["outstanding"] == Decimal("600000")
    assert totals["payment_status"] == "PARTIALLY_PAID"


def test_fx_gain_is_recognized_on_settlement(db_session, ap_context):
    ctx = ap_context
    # 1000 USD @ 600 = 600,000 XAF liability
    bill = create_supplier_bill(
        db_session, ctx["user"].id,
        _bill(ctx, "AP-004", net="600000", currency="USD", rate="600.000000"),
    )
    post_supplier_bill(db_session, bill.id, ctx["user"].id)

    # Pay 1000 USD @ 590 = 590,000 XAF cash -> 10,000 gain
    settlement = create_settlement(db_session, ctx["user"].id, SettlementCreateSchema(
        third_party_id=ctx["supplier"].id,
        settlement_date=date(2090, 1, 25),
        journal_code="BQ1",
        treasury_account_code="521",
        reference="PAY-002",
        description="USD settlement",
        currency_code="USD",
        exchange_rate=Decimal("590.000000"),
        allocations=[SettlementAllocationSchema(bill_id=bill.id, allocated_foreign_amount=Decimal("1000.00"))],
    ))

    assert settlement.fx_gain_loss_base == Decimal("10000")
    posted = post_settlement(db_session, settlement.id, ctx["user"].id)

    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == posted.journal_entry_id).all()
    gain_account = db_session.query(Account).filter(Account.code == "776").first()
    gain_lines = [l for l in lines if l.account_id == gain_account.id]
    assert len(gain_lines) == 1
    assert gain_lines[0].base_credit == Decimal("10000")
    assert sum(l.base_debit for l in lines) == sum(l.base_credit for l in lines)

    totals = get_bill_totals(db_session, bill)
    assert totals["payment_status"] == "PAID"


def test_over_allocation_is_rejected(db_session, ap_context):
    ctx = ap_context
    bill = create_supplier_bill(db_session, ctx["user"].id, _bill(ctx, "AP-005", net="500000"))
    post_supplier_bill(db_session, bill.id, ctx["user"].id)

    with pytest.raises(ValueError) as excinfo:
        create_settlement(db_session, ctx["user"].id, SettlementCreateSchema(
            third_party_id=ctx["supplier"].id,
            settlement_date=date(2090, 1, 20),
            journal_code="BQ1",
            treasury_account_code="521",
            reference="PAY-003",
            description="Over payment",
            allocations=[SettlementAllocationSchema(bill_id=bill.id, allocated_foreign_amount=Decimal("600000"))],
        ))

    assert "exceeds outstanding balance" in str(excinfo.value)

def test_tax_account_is_postable_and_needs_no_third_party(db_session, ap_context):
    """447 must be postable and must NOT require a tiers dimension."""
    from app.services.ledger_service import (
        create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema,
    )

    ctx = ap_context

    tax_account = db_session.query(Account).filter(Account.code == "447").first()
    assert tax_account is not None, "Account 447 missing — run migrations."
    assert tax_account.is_postable is True
    assert tax_account.requires_third_party is False

    entry = create_and_validate_entry(
        db_session,
        ctx["user"].id,
        JournalEntryCreateSchema(
            journal_code="ACH",
            fiscal_year_code=ctx["fy"].code,
            period_id=ctx["period"].id,
            entry_date=date(2090, 1, 12),
            description="WHT without tiers",
            lines=[
                JournalLineSchema(
                    account_code=ctx["expense"].code,
                    base_debit=Decimal("100000"),
                ),
                JournalLineSchema(
                    account_code="447",
                    base_credit=Decimal("100000"),
                    third_party_id=None,
                ),
            ],
        ),
    )

    assert entry.status == EntryStatus.DRAFT
    assert entry.voucher_number.startswith("ACH-2090-")


def test_control_account_still_requires_third_party(db_session, ap_context):
    """401 must still reject a line with no tiers."""
    from app.services.ledger_service import (
        create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema,
    )

    ctx = ap_context

    with pytest.raises(ValueError) as excinfo:
        create_and_validate_entry(
            db_session,
            ctx["user"].id,
            JournalEntryCreateSchema(
                journal_code="ACH",
                fiscal_year_code=ctx["fy"].code,
                period_id=ctx["period"].id,
                entry_date=date(2090, 1, 12),
                description="Missing tiers",
                lines=[
                    JournalLineSchema(
                        account_code=ctx["expense"].code,
                        base_debit=Decimal("100000"),
                    ),
                    JournalLineSchema(
                        account_code="401",
                        base_credit=Decimal("100000"),
                        third_party_id=None,
                    ),
                ],
            ),
        )

    assert "requires a linked Third Party" in str(excinfo.value)