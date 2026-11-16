import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from app.models.enums import EntryStatus, UserRole, NormalBalance, PeriodStatus, FiscalYearStatus
from app.models.user import User
from app.models.account import Account
from app.models.ledger import JournalEntry, JournalLine
from app.models.period import FiscalYear, AccountingPeriod
from app.models.master_data import AccountingJournal
from app.models.currency import Currency
from app.services.reporting_service import get_trial_balance, close_period, GLFilters, get_general_ledger
from app.services.ledger_service import create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema


@pytest.fixture
def setup_reporting_test(db_session):
    user = User(email="daf@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)

    fy = FiscalYear(code="2040", start_date=date(2040, 1, 1), end_date=date(2040, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    p1 = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2040, 1, 1),
                          end_date=date(2040, 1, 31), status=PeriodStatus.OPEN)
    p2 = AccountingPeriod(fiscal_year_id=fy.id, period_number=2, start_date=date(2040, 2, 1),
                          end_date=date(2040, 2, 28), status=PeriodStatus.OPEN)
    db_session.add_all([p1, p2])
    db_session.flush()

    journal = AccountingJournal(code="TST5", label="Test", journal_type="MANUAL")
    db_session.add(journal)
    db_session.flush()

    acc_bank = Account(code="951", label="Bank", account_class=5, normal_balance=NormalBalance.DEBIT, is_postable=True)
    acc_cap = Account(code="961", label="Capital", account_class=1, normal_balance=NormalBalance.CREDIT,
                      is_postable=True)
    db_session.add_all([acc_bank, acc_cap])
    db_session.flush()

    return {"user": user, "fy": fy, "p1": p1, "p2": p2, "journal": journal, "acc_bank": acc_bank, "acc_cap": acc_cap}


def test_trial_balance_calculations(db_session, setup_reporting_test):
    ctx = setup_reporting_test

    # Post a balanced entry in Period 1
    data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code, fiscal_year_code=ctx["fy"].code, period_id=ctx["p1"].id,
        entry_date=date(2040, 1, 15), description="Initial Capital",
        lines=[
            JournalLineSchema(account_code=ctx["acc_bank"].code, base_debit=Decimal("10000")),
            JournalLineSchema(account_code=ctx["acc_cap"].code, base_credit=Decimal("10000"))
        ]
    )
    entry = create_and_validate_entry(db_session, ctx["user"].id, data)
    entry.status = EntryStatus.POSTED
    entry.posted_at = datetime.now(timezone.utc)
    db_session.commit()

    # Calculate Trial Balance as of end of Period 1
    rows = get_trial_balance(db_session, ctx["fy"].id, date(2040, 1, 31))

    assert len(rows) == 2
    bank_row = next(r for r in rows if r.account_code == "951")
    assert bank_row.movement_debit == Decimal("10000")
    assert bank_row.closing_debit == Decimal("10000")
    assert bank_row.closing_credit == Decimal("0")


def test_period_lockdown_prevents_posting(db_session, setup_reporting_test):
    ctx = setup_reporting_test

    # Close Period 1
    closed_period = close_period(db_session, ctx["p1"].id, ctx["user"].id)
    assert closed_period.status == PeriodStatus.CLOSED

    # Attempt to post an entry into the CLOSED Period 1
    data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code, fiscal_year_code=ctx["fy"].code, period_id=ctx["p1"].id,
        entry_date=date(2040, 1, 20), description="Late Entry",
        lines=[
            JournalLineSchema(account_code=ctx["acc_bank"].code, base_debit=Decimal("500")),
            JournalLineSchema(account_code=ctx["acc_cap"].code, base_credit=Decimal("500"))
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        create_and_validate_entry(db_session, ctx["user"].id, data)

    assert "Accounting period is not OPEN" in str(excinfo.value)