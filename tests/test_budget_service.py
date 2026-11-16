import pytest
from decimal import Decimal
from datetime import date, datetime, timezone
from app.models.enums import EntryStatus, UserRole, NormalBalance, PeriodStatus, FiscalYearStatus
from app.models.user import User
from app.models.account import Account
from app.models.ledger import JournalEntry, JournalLine
from app.models.period import FiscalYear, AccountingPeriod
from app.models.master_data import AccountingJournal, BudgetLine, Fund, Project
from app.models.settings import OrganizationSetting
from app.models.currency import Currency
from app.services.budget_service import get_budget_vs_actual
from app.services.ledger_service import create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema


@pytest.fixture
def setup_budget_test(db_session):
    user = User(email="budget@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)

    fy = FiscalYear(code="2050", start_date=date(2050, 1, 1), end_date=date(2050, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    p1 = AccountingPeriod(fiscal_year_id=fy.id, period_number=1, start_date=date(2050, 1, 1), end_date=date(2050, 1, 31), status=PeriodStatus.OPEN)
    db_session.add(p1)
    db_session.flush()

    journal = AccountingJournal(code="TST6", label="Test Budget", journal_type="MANUAL")
    db_session.add(journal)
    db_session.flush()

    fund = Fund(code="USADF", label="USAID Fund", currency_code="USD", is_restricted=True)
    db_session.add(fund)
    db_session.flush()

    project = Project(code="PRJ1", label="Health Project", fund_id=fund.id)
    db_session.add(project)
    db_session.flush()

    acc_exp = Account(code="960", label="Test Expense", account_class=6, normal_balance=NormalBalance.DEBIT, is_postable=True)
    acc_bank = Account(code="962", label="Test Bank", account_class=5, normal_balance=NormalBalance.DEBIT, is_postable=True)
    db_session.add_all([acc_exp, acc_bank])
    db_session.flush()

    # Budget line: 1,000,000 XAF approved
    budget_line = BudgetLine(
        account_id=acc_exp.id,
        project_id=project.id,
        fund_id=fund.id,
        fiscal_year_id=fy.id,
        approved_amount=Decimal("1000000"),
    )
    db_session.add(budget_line)
    db_session.flush()

    return {
        "user": user, "fy": fy, "p1": p1, "journal": journal,
        "fund": fund, "project": project, "acc_exp": acc_exp,
        "acc_bank": acc_bank, "budget_line": budget_line,
    }


def test_budget_vs_actual_xaf_view(db_session, setup_budget_test):
    ctx = setup_budget_test

    # CRITICAL: Enable budget control so budget_line_id is tracked on journal lines.
    # Without this, create_and_validate_entry sets budget_line_id = None by design.
    settings = db_session.query(OrganizationSetting).first()
    settings.budget_control_enabled = True
    db_session.commit()

    # Post an expense of 300,000 XAF against the budget line
    data = JournalEntryCreateSchema(
        journal_code=ctx["journal"].code,
        fiscal_year_code=ctx["fy"].code,
        period_id=ctx["p1"].id,
        entry_date=date(2050, 1, 15),
        description="Test expense",
        lines=[
            JournalLineSchema(
                account_code=ctx["acc_exp"].code,
                base_debit=Decimal("300000"),
                budget_line_id=ctx["budget_line"].id,
                fund_id=ctx["fund"].id,
                project_id=ctx["project"].id,
            ),
            JournalLineSchema(
                account_code=ctx["acc_bank"].code,
                base_credit=Decimal("300000"),
            ),
        ],
    )
    entry = create_and_validate_entry(db_session, ctx["user"].id, data)
    entry.status = EntryStatus.POSTED
    entry.posted_at = datetime.now(timezone.utc)
    db_session.commit()

    # Generate the report in XAF view
    rows = get_budget_vs_actual(
        db_session,
        fiscal_year_id=ctx["fy"].id,
        fund_id=ctx["fund"].id,
        view_currency="XAF",
    )

    assert len(rows) == 1
    row = rows[0]
    assert row.approved_budget == Decimal("1000000")
    assert row.actual_posted == Decimal("300000")
    assert row.committed == Decimal("0")
    assert row.remaining == Decimal("700000")
    assert row.burn_rate == Decimal("30.0")