import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from app.models.enums import EntryStatus, UserRole, NormalBalance, PeriodStatus, FiscalYearStatus
from app.models.user import User
from app.models.account import Account
from app.models.period import FiscalYear, AccountingPeriod
from app.models.master_data import AccountingJournal
from app.models.currency import Currency
from app.services.statements_service import get_compte_de_resultat, get_bilan
from app.services.ledger_service import create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema


@pytest.fixture
def setup_statements_test(db_session):
    user = User(email="stmt@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)

    fy = FiscalYear(code="2060", start_date=date(2060, 1, 1), end_date=date(2060, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    p1 = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2060, 1, 1), end_date=date(2060, 1, 31), status=PeriodStatus.OPEN)
    db_session.add(p1)
    db_session.flush()

    journal = AccountingJournal(code="TST7", label="Test Statements", journal_type="MANUAL")
    db_session.add(journal)
    db_session.flush()

    acc_exp = Account(code="970", label="Test Expense", account_class=6, normal_balance=NormalBalance.DEBIT, is_postable=True)
    acc_rev = Account(code="971", label="Test Revenue", account_class=7, normal_balance=NormalBalance.CREDIT, is_postable=True)
    acc_bank = Account(code="972", label="Test Bank", account_class=5, normal_balance=NormalBalance.DEBIT, is_postable=True)
    db_session.add_all([acc_exp, acc_rev, acc_bank])
    db_session.flush()

    return {"user": user, "fy": fy, "p1": p1, "journal": journal, "acc_exp": acc_exp, "acc_rev": acc_rev, "acc_bank": acc_bank}


def test_compte_de_resultat_calculations(db_session, setup_statements_test):
    ctx = setup_statements_test

    # Post revenue: 500,000
    rev_data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code, fiscal_year_code=ctx["fy"].code, period_id=ctx["p1"].id,
        entry_date=date(2060, 1, 10), description="Revenue",
        lines=[
            JournalLineSchema(account_code=ctx["acc_bank"].code, base_debit=Decimal("500000")),
            JournalLineSchema(account_code=ctx["acc_rev"].code, base_credit=Decimal("500000")),
        ]
    )
    entry1 = create_and_validate_entry(db_session, ctx["user"].id, rev_data)
    entry1.status = EntryStatus.POSTED
    entry1.posted_at = datetime.now(timezone.utc)

    # Post expense: 200,000
    exp_data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code, fiscal_year_code=ctx["fy"].code, period_id=ctx["p1"].id,
        entry_date=date(2060, 1, 15), description="Expense",
        lines=[
            JournalLineSchema(account_code=ctx["acc_exp"].code, base_debit=Decimal("200000")),
            JournalLineSchema(account_code=ctx["acc_bank"].code, base_credit=Decimal("200000")),
        ]
    )
    entry2 = create_and_validate_entry(db_session, ctx["user"].id, exp_data)
    entry2.status = EntryStatus.POSTED
    entry2.posted_at = datetime.now(timezone.utc)
    db_session.commit()

    # Generate Compte de Résultat
    cr = get_compte_de_resultat(db_session, ctx["fy"].id)

    assert cr.total_produits == Decimal("500000")
    assert cr.total_charges == Decimal("200000")
    assert cr.resultat == Decimal("300000")  # Profit


def test_bilan_structure(db_session, setup_statements_test):
    ctx = setup_statements_test

    # Post capital injection: 1,000,000
    # Need a capital account (Class 1)
    acc_cap = Account(code="973", label="Test Capital", account_class=1, normal_balance=NormalBalance.CREDIT, is_postable=True)
    db_session.add(acc_cap)
    db_session.flush()

    cap_data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code, fiscal_year_code=ctx["fy"].code, period_id=ctx["p1"].id,
        entry_date=date(2060, 1, 5), description="Capital",
        lines=[
            JournalLineSchema(account_code=ctx["acc_bank"].code, base_debit=Decimal("1000000")),
            JournalLineSchema(account_code=acc_cap.code, base_credit=Decimal("1000000")),
        ]
    )
    entry = create_and_validate_entry(db_session, ctx["user"].id, cap_data)
    entry.status = EntryStatus.POSTED
    entry.posted_at = datetime.now(timezone.utc)
    db_session.commit()

    bilan = get_bilan(db_session, ctx["fy"].id)

    # Bank is Actif (Debit balance), Capital is Passif (Credit balance)
    assert bilan.total_actif == Decimal("1000000")
    assert bilan.total_passif == Decimal("1000000")
    assert bilan.total_actif == bilan.total_passif