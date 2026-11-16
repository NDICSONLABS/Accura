import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from app.models.enums import EntryStatus, UserRole, NormalBalance, PeriodStatus, FiscalYearStatus, BudgetEnforcementMode
from app.models.user import User
from app.models.account import Account
from app.models.ledger import JournalEntry, JournalLine
from app.models.period import FiscalYear, AccountingPeriod
from app.models.master_data import AccountingJournal, ThirdParty, JournalSequence
from app.models.settings import OrganizationSetting
from app.models.currency import Currency  # CRITICAL: Registers 'currencies' table in metadata
from app.services.ledger_service import (
    create_and_validate_entry, post_journal_entry, reverse_journal_entry,
    JournalEntryCreateSchema, JournalLineSchema
)


@pytest.fixture
def setup_ledger_test(db_session):
    # 1. Setup Settings
    settings = db_session.query(OrganizationSetting).first()
    settings.maker_checker_approval_enabled = True
    settings.tax_withholding_enabled = True
    db_session.commit()

    # 2. Setup Users
    maker = User(email="maker@test.com", password_hash="hash", role=UserRole.ACCOUNTANT_PREPARER)
    approver = User(email="approver@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add_all([maker, approver])
    db_session.flush()  # Generate IDs

    # 3. Setup Period
    fy = FiscalYear(code="2030", start_date=date(2030, 1, 1), end_date=date(2030, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()  # Generate ID

    period = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2030, 1, 1),
                              end_date=date(2030, 1, 31), status=PeriodStatus.OPEN)
    db_session.add(period)

    # 4. Setup Journal
    journal = AccountingJournal(code="TST4", label="Test Journal", journal_type="MANUAL")
    db_session.add(journal)
    db_session.flush()  # Generate ID

    # 5. Setup Accounts (Unique codes to avoid seed collision)
    acc_expense = Account(code="901", label="Test Achats", account_class=6, normal_balance=NormalBalance.DEBIT,
                          is_postable=True)
    acc_bank = Account(code="921", label="Test Banque", account_class=5, normal_balance=NormalBalance.DEBIT,
                       is_postable=True)
    acc_supplier = Account(code="941", label="Test Fournisseurs", account_class=4, normal_balance=NormalBalance.CREDIT,
                           is_postable=True, requires_third_party=True)
    db_session.add_all([acc_expense, acc_bank, acc_supplier])
    db_session.flush()  # CRITICAL: Generate IDs before referencing them!

    # 6. Setup Third Party (acc_supplier.id is now guaranteed to be an integer)
    tp = ThirdParty(name="Test Supplier", account_id=acc_supplier.id)
    db_session.add(tp)
    db_session.flush()

    return {
        "maker": maker, "approver": approver, "fy": fy, "period": period,
        "journal": journal, "acc_expense": acc_expense, "acc_bank": acc_bank,
        "acc_supplier": acc_supplier, "tp": tp
    }


def test_class_4_requires_third_party(db_session, setup_ledger_test):
    ctx = setup_ledger_test
    data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["period"].id,
        entry_date=date(2030, 1, 15),
        description="Test Class 4",
        lines=[
            JournalLineSchema(account_code=ctx["acc_expense"].code, base_debit=Decimal("1000")),
            JournalLineSchema(account_code=ctx["acc_supplier"].code, base_credit=Decimal("1000"), third_party_id=None)
        ]
    )

    with pytest.raises(ValueError) as excinfo:
        create_and_validate_entry(db_session, ctx["maker"].id, data)

    assert "requires a linked Third Party" in str(excinfo.value)


def test_maker_checker_prevents_self_approval(db_session, setup_ledger_test):
    ctx = setup_ledger_test
    data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["period"].id,
        entry_date=date(2030, 1, 15),
        description="Test Maker-Checker",
        lines=[
            JournalLineSchema(account_code=ctx["acc_expense"].code, base_debit=Decimal("1000")),
            JournalLineSchema(account_code=ctx["acc_supplier"].code, base_credit=Decimal("1000"),
                              third_party_id=ctx["tp"].id)
        ]
    )

    entry = create_and_validate_entry(db_session, ctx["maker"].id, data)
    assert entry.status == EntryStatus.DRAFT

    with pytest.raises(ValueError) as excinfo:
        post_journal_entry(db_session, entry.id, ctx["maker"].id)

    assert "Maker-Checker rule violated" in str(excinfo.value)

    posted_entry = post_journal_entry(db_session, entry.id, ctx["approver"].id)
    assert posted_entry.status == EntryStatus.POSTED


def test_reversal_creates_opposite_entry(db_session, setup_ledger_test):
    ctx = setup_ledger_test
    data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["period"].id,
        entry_date=date(2030, 1, 15),
        description="Test Reversal",
        lines=[
            JournalLineSchema(account_code=ctx["acc_expense"].code, base_debit=Decimal("5000")),
            JournalLineSchema(account_code=ctx["acc_bank"].code, base_credit=Decimal("5000"))
        ]
    )

    entry = create_and_validate_entry(db_session, ctx["maker"].id, data)
    posted_entry = post_journal_entry(db_session, entry.id, ctx["approver"].id)

    reversal_entry = reverse_journal_entry(db_session, posted_entry.id, ctx["approver"].id, date(2030, 1, 20))

    assert reversal_entry.status == EntryStatus.POSTED
    assert f"REV-{posted_entry.voucher_number}" in reversal_entry.reference

    rev_lines = db_session.query(JournalLine).filter(JournalLine.entry_id == reversal_entry.id).all()
    assert rev_lines[0].base_debit == Decimal("0")
    assert rev_lines[0].base_credit == Decimal("5000")