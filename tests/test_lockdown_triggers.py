import pytest
from sqlalchemy import text
from decimal import Decimal
from datetime import date, datetime, timezone
from app.models.enums import EntryStatus, UserRole, NormalBalance, PeriodStatus, FiscalYearStatus
from app.models.user import User
from app.models.account import Account
from app.models.ledger import JournalEntry, JournalLine
from app.models.period import FiscalYear, AccountingPeriod
from app.models.master_data import AccountingJournal
from app.models.currency import Currency


def test_audit_log_immutable(db_session):
    db_session.execute(text("""
                            INSERT INTO audit_log (user_id, timestamp, ip_address, entity_type, entity_id, action)
                            VALUES (NULL, NOW(), '127.0.0.1', 'test', 1, 'CREATE')
                            """))
    db_session.commit()

    with pytest.raises(Exception) as excinfo:
        db_session.execute(text("UPDATE audit_log SET action = 'UPDATE' WHERE entity_id = 1"))
        db_session.commit()
    assert "Audit log is append-only" in str(excinfo.value.orig)


def test_posted_entry_and_lines_immutable(db_session):
    user = User(email="test@test.com", password_hash="hash", role=UserRole.ACCOUNTANT_PREPARER)
    db_session.add(user)

    # Use unique year to avoid seed data collisions
    fy = FiscalYear(code="2099", start_date=date(2099, 1, 1), end_date=date(2099, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    period = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2099, 1, 1),
                              end_date=date(2099, 1, 31), status=PeriodStatus.OPEN)
    db_session.add(period)

    journal = AccountingJournal(code="TST1", label="Test Journal", journal_type="MANUAL")
    db_session.add(journal)

    acc1 = Account(code="991", label="Test Capital", account_class=1, normal_balance=NormalBalance.CREDIT,
                   is_postable=True)
    acc2 = Account(code="992", label="Test Banque", account_class=5, normal_balance=NormalBalance.DEBIT,
                   is_postable=True)
    db_session.add_all([acc1, acc2])
    db_session.flush()

    entry = JournalEntry(
        journal_id=journal.id, period_id=period.id, entry_date=date(2099, 1, 15),
        voucher_number="TST1-2099-0001", description="Test Draft", status=EntryStatus.DRAFT,
        created_by_id=user.id
    )
    db_session.add(entry)
    db_session.flush()

    line1 = JournalLine(entry_id=entry.id, account_id=acc1.id, currency_code="XAF", exchange_rate=Decimal("1.000000"),
                        base_credit=Decimal("1000"))
    line2 = JournalLine(entry_id=entry.id, account_id=acc2.id, currency_code="XAF", exchange_rate=Decimal("1.000000"),
                        base_debit=Decimal("1000"))
    db_session.add_all([line1, line2])
    db_session.commit()

    entry.status = EntryStatus.POSTED
    entry.posted_at = datetime.now(timezone.utc)
    db_session.commit()

    with pytest.raises(Exception) as excinfo:
        line1.base_credit = Decimal("2000")
        db_session.commit()
    assert "Cannot modify lines of a POSTED journal entry" in str(excinfo.value.orig)


def test_unbalanced_posting_fails(db_session):
    user = User(email="test2@test.com", password_hash="hash", role=UserRole.ACCOUNTANT_PREPARER)
    db_session.add(user)

    fy = FiscalYear(code="2098", start_date=date(2098, 1, 1), end_date=date(2098, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    period = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2098, 1, 1),
                              end_date=date(2098, 1, 31), status=PeriodStatus.OPEN)
    db_session.add(period)

    journal = AccountingJournal(code="TST2", label="Test Journal 2", journal_type="MANUAL")
    db_session.add(journal)

    acc1 = Account(code="993", label="Test Capital 2", account_class=1, normal_balance=NormalBalance.CREDIT,
                   is_postable=True)
    acc2 = Account(code="994", label="Test Banque 2", account_class=5, normal_balance=NormalBalance.DEBIT,
                   is_postable=True)
    db_session.add_all([acc1, acc2])
    db_session.flush()

    entry = JournalEntry(
        journal_id=journal.id, period_id=period.id, entry_date=date(2098, 1, 15),
        voucher_number="TST2-2098-0001", description="Unbalanced", status=EntryStatus.DRAFT,
        created_by_id=user.id
    )
    db_session.add(entry)
    db_session.flush()

    line1 = JournalLine(entry_id=entry.id, account_id=acc1.id, currency_code="XAF", exchange_rate=Decimal("1.000000"),
                        base_credit=Decimal("1000"))
    line2 = JournalLine(entry_id=entry.id, account_id=acc2.id, currency_code="XAF", exchange_rate=Decimal("1.000000"),
                        base_debit=Decimal("500"))
    db_session.add_all([line1, line2])
    db_session.commit()

    with pytest.raises(Exception) as excinfo:
        entry.status = EntryStatus.POSTED
        entry.posted_at = datetime.now(timezone.utc)
        db_session.commit()
    assert "unbalanced or zero" in str(excinfo.value.orig)