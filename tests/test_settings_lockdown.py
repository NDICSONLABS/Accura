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
from app.services.settings_service import update_settings, SettingsUpdateSchema, get_settings
from app.models.enums import BudgetEnforcementMode


def test_safe_toggle_locking_prevents_disabling_multicurrency(db_session):
    settings = get_settings(db_session)
    settings.multi_currency_enabled = True
    db_session.commit()

    user = User(email="test_fx@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)

    fy = FiscalYear(code="2099", start_date=date(2099, 1, 1), end_date=date(2099, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    period = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2099, 1, 1),
                              end_date=date(2099, 1, 31), status=PeriodStatus.OPEN)
    db_session.add(period)

    journal = AccountingJournal(code="TST3", label="Test FX", journal_type="MANUAL")
    db_session.add(journal)

    acc1 = Account(code="995", label="Test FX Account", account_class=5, normal_balance=NormalBalance.DEBIT,
                   is_postable=True)
    acc2 = Account(code="996", label="Test FX Counter", account_class=7, normal_balance=NormalBalance.CREDIT,
                   is_postable=True)
    db_session.add_all([acc1, acc2])
    db_session.flush()

    entry = JournalEntry(
        journal_id=journal.id, period_id=period.id, entry_date=date(2099, 1, 15),
        voucher_number="TST3-2099-0001", description="FX Test", status=EntryStatus.DRAFT,
        created_by_id=user.id
    )
    db_session.add(entry)
    db_session.flush()

    line1 = JournalLine(entry_id=entry.id, account_id=acc1.id, currency_code="USD", exchange_rate=Decimal("600.000000"),
                        base_debit=Decimal("600000"), foreign_debit=Decimal("1000.00"))
    line2 = JournalLine(entry_id=entry.id, account_id=acc2.id, currency_code="XAF", exchange_rate=Decimal("1.000000"),
                        base_credit=Decimal("600000"))
    db_session.add_all([line1, line2])
    db_session.commit()

    entry.status = EntryStatus.POSTED
    entry.posted_at = datetime.now(timezone.utc)
    db_session.commit()

    updates = SettingsUpdateSchema(
        multi_currency_enabled=False,
        donor_fund_tracking_enabled=False,
        project_cost_center_enabled=False,
        budget_control_enabled=False,
        budget_enforcement_mode=BudgetEnforcementMode.NONE,
        maker_checker_approval_enabled=False,
        tax_withholding_enabled=False
    )

    with pytest.raises(ValueError) as excinfo:
        update_settings(db_session, updates)

    assert "Cannot disable multi-currency" in str(excinfo.value)


def test_safe_toggle_allows_disabling_if_no_posted_fx(db_session):
    settings = get_settings(db_session)
    settings.multi_currency_enabled = True
    db_session.commit()

    updates = SettingsUpdateSchema(
        multi_currency_enabled=False,
        donor_fund_tracking_enabled=False,
        project_cost_center_enabled=False,
        budget_control_enabled=False,
        budget_enforcement_mode=BudgetEnforcementMode.NONE,
        maker_checker_approval_enabled=False,
        tax_withholding_enabled=False
    )

    updated_settings = update_settings(db_session, updates)
    assert updated_settings.multi_currency_enabled is False