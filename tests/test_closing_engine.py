import calendar
import pytest
from decimal import Decimal
from datetime import date

from app.models.enums import (
    UserRole, PeriodStatus, FiscalYearStatus, EntryStatus, FxDirection,
)
from app.models.user import User
from app.models.account import Account
from app.models.master_data import ThirdParty
from app.models.period import FiscalYear, AccountingPeriod
from app.models.ledger import JournalLine
from app.models.closing import FxRevaluationRun, FxRevaluationLine, FiscalYearClose
from app.models.settings import OrganizationSetting
from app.models.currency import Currency
from app.services.closing_service import (
    soft_lock_period, get_fx_exposures, create_fx_revaluation, reverse_fx_revaluation,
    get_closing_checklist, close_fiscal_year, open_next_fiscal_year, carry_forward_result,
    FxRevaluationSchema, FxRateSchema,
)
from app.services.ledger_service import (
    create_and_validate_entry, post_journal_entry,
    JournalEntryCreateSchema, JournalLineSchema,
)
from app.services.reporting_service import get_trial_balance
from app.services.statements_service import get_compte_de_resultat


@pytest.fixture
def closing_context(db_session):
    settings = db_session.query(OrganizationSetting).first()
    settings.maker_checker_approval_enabled = False
    settings.multi_currency_enabled = True
    settings.tax_withholding_enabled = False
    settings.budget_control_enabled = False
    db_session.commit()

    user = User(email="closing@test.com", password_hash="hash", role=UserRole.FINANCE_MANAGER_APPROVER)
    db_session.add(user)
    db_session.flush()

    fy = FiscalYear(code="2097", start_date=date(2097, 1, 1),
                    end_date=date(2097, 12, 31), status=FiscalYearStatus.OPEN)
    db_session.add(fy)
    db_session.flush()

    periods = []
    for month in range(1, 13):
        last_day = calendar.monthrange(2097, month)[1]
        period = AccountingPeriod(
            fiscal_year_id=fy.id, period_number=month,
            start_date=date(2097, month, 1), end_date=date(2097, month, last_day),
            status=PeriodStatus.OPEN,
        )
        db_session.add(period)
        db_session.flush()
        periods.append(period)

    receivable = db_session.query(Account).filter(Account.code == "411").first()
    donor = ThirdParty(name="CLOSING DONOR", account_id=receivable.id)
    db_session.add(donor)
    db_session.flush()

    expense = Account(code="996", label="Closing Expense", account_class=6,
                      normal_balance="DEBIT", is_postable=True)
    revenue = Account(code="997", label="Closing Revenue", account_class=7,
                      normal_balance="CREDIT", is_postable=True)
    db_session.add_all([expense, revenue])
    db_session.flush()

    return {
        "user": user, "fy": fy, "periods": periods, "donor": donor,
        "expense": expense, "revenue": revenue,
        "receivable": receivable,
        "bank": db_session.query(Account).filter(Account.code == "521").first(),
    }


def _post(db, ctx, period, description, lines, entry_day=15):
    entry = create_and_validate_entry(db, ctx["user"].id, JournalEntryCreateSchema(
        journal_code="OD", fiscal_year_code=ctx["fy"].code, period_id=period.id,
        entry_date=date(2097, period.period_number, entry_day),
        description=description, lines=lines,
    ))
    return post_journal_entry(db, entry.id, ctx["user"].id)


def test_fx_revaluation_posts_latent_loss_to_478(db_session, closing_context):
    ctx = closing_context
    p1, p12 = ctx["periods"][0], ctx["periods"][-1]

    # Receivable 1000 USD @ 600 = 600,000 XAF
    _post(db_session, ctx, p1, "Foreign receivable", [
        JournalLineSchema(account_code="411", third_party_id=ctx["donor"].id,
                          currency_code="USD", exchange_rate=Decimal("600.000000"),
                          foreign_debit=Decimal("1000.00"), base_debit=Decimal("600000")),
        JournalLineSchema(account_code=ctx["revenue"].code, base_credit=Decimal("600000")),
    ])

    exposures = get_fx_exposures(db_session, p12.end_date)
    assert len(exposures) == 1
    assert exposures[0]["foreign_balance"] == Decimal("1000.00")

    run = create_fx_revaluation(db_session, ctx["user"].id, FxRevaluationSchema(
        period_id=p12.id,
        rates=[FxRateSchema(currency_code="USD", closing_rate=Decimal("590.000000"))],
    ))

    assert run.status == EntryStatus.POSTED
    assert run.total_latent_loss_base == Decimal("10000")
    assert run.total_latent_gain_base == Decimal("0")

    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == run.journal_entry_id).all()
    assert sum(l.base_debit for l in lines) == sum(l.base_credit for l in lines) == Decimal("10000")

    acct_478 = db_session.query(Account).filter(Account.code == "478").first()
    debit_478 = [l for l in lines if l.account_id == acct_478.id]
    assert len(debit_478) == 1
    assert debit_478[0].base_debit == Decimal("10000")

    detail_line = db_session.query(FxRevaluationLine).filter(FxRevaluationLine.run_id == run.id).first()
    assert detail_line.direction == FxDirection.LOSS
    assert detail_line.revalued_base == Decimal("590000")


def test_fx_revaluation_posts_latent_gain_to_479(db_session, closing_context):
    ctx = closing_context
    p1, p12 = ctx["periods"][0], ctx["periods"][-1]

    _post(db_session, ctx, p1, "Foreign receivable", [
        JournalLineSchema(account_code="411", third_party_id=ctx["donor"].id,
                          currency_code="USD", exchange_rate=Decimal("600.000000"),
                          foreign_debit=Decimal("1000.00"), base_debit=Decimal("600000")),
        JournalLineSchema(account_code=ctx["revenue"].code, base_credit=Decimal("600000")),
    ])

    run = create_fx_revaluation(db_session, ctx["user"].id, FxRevaluationSchema(
        period_id=p12.id,
        rates=[FxRateSchema(currency_code="USD", closing_rate=Decimal("615.000000"))],
    ))

    assert run.total_latent_gain_base == Decimal("15000")
    acct_479 = db_session.query(Account).filter(Account.code == "479").first()
    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == run.journal_entry_id).all()
    credit_479 = [l for l in lines if l.account_id == acct_479.id]
    assert credit_479[0].base_credit == Decimal("15000")


def test_revaluation_reversal_restores_historical_balance(db_session, closing_context):
    ctx = closing_context
    p1, p12 = ctx["periods"][0], ctx["periods"][-1]

    _post(db_session, ctx, p1, "Foreign receivable", [
        JournalLineSchema(account_code="411", third_party_id=ctx["donor"].id,
                          currency_code="USD", exchange_rate=Decimal("600.000000"),
                          foreign_debit=Decimal("1000.00"), base_debit=Decimal("600000")),
        JournalLineSchema(account_code=ctx["revenue"].code, base_credit=Decimal("600000")),
    ])

    run = create_fx_revaluation(db_session, ctx["user"].id, FxRevaluationSchema(
        period_id=p12.id,
        rates=[FxRateSchema(currency_code="USD", closing_rate=Decimal("590.000000"))],
    ))

    reversed_run = reverse_fx_revaluation(db_session, run.id, ctx["user"].id, date(2097, 12, 31))
    assert reversed_run.reversal_entry_id is not None

    exposures = get_fx_exposures(db_session, p12.end_date)
    assert exposures[0]["historical_base"] == Decimal("600000")

    tb = get_trial_balance(db_session, ctx["fy"].id, ctx["fy"].end_date)
    assert sum(r.closing_debit for r in tb) == sum(r.closing_credit for r in tb)


def test_year_close_zeroes_management_accounts(db_session, closing_context):
    ctx = closing_context
    p1 = ctx["periods"][0]

    _post(db_session, ctx, p1, "Revenue", [
        JournalLineSchema(account_code=ctx["bank"].code, base_debit=Decimal("500000")),
        JournalLineSchema(account_code=ctx["revenue"].code, base_credit=Decimal("500000")),
    ])
    _post(db_session, ctx, p1, "Expense", [
        JournalLineSchema(account_code=ctx["expense"].code, base_debit=Decimal("200000")),
        JournalLineSchema(account_code=ctx["bank"].code, base_credit=Decimal("200000")),
    ])

    for period in ctx["periods"][:-1]:
        soft_lock_period(db_session, period.id, ctx["user"].id)

    checklist = get_closing_checklist(db_session, ctx["fy"].id)
    assert checklist["ready"] is True
    assert checklist["result"] == Decimal("300000")

    record = close_fiscal_year(db_session, ctx["fy"].id, ctx["user"].id)
    assert record.result_base == Decimal("300000")

    db_session.refresh(ctx["fy"])
    assert ctx["fy"].status == FiscalYearStatus.CLOSED

    cr = get_compte_de_resultat(db_session, ctx["fy"].id)
    assert cr.total_charges == Decimal("0")
    assert cr.total_produits == Decimal("0")

    acct_131 = db_session.query(Account).filter(Account.code == "131").first()
    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == record.result_entry_id).all()
    result_line = [l for l in lines if l.account_id == acct_131.id][0]
    assert result_line.base_credit == Decimal("300000")

    tb = get_trial_balance(db_session, ctx["fy"].id, ctx["fy"].end_date)
    assert sum(r.closing_debit for r in tb) == sum(r.closing_credit for r in tb)


def test_carry_forward_result_moves_131_to_121(db_session, closing_context):
    ctx = closing_context
    p1 = ctx["periods"][0]

    _post(db_session, ctx, p1, "Revenue", [
        JournalLineSchema(account_code=ctx["bank"].code, base_debit=Decimal("400000")),
        JournalLineSchema(account_code=ctx["revenue"].code, base_credit=Decimal("400000")),
    ])

    for period in ctx["periods"][:-1]:
        soft_lock_period(db_session, period.id, ctx["user"].id)

    close_fiscal_year(db_session, ctx["fy"].id, ctx["user"].id)
    next_fy = open_next_fiscal_year(db_session, ctx["fy"].id)
    assert next_fy.code == "2098"

    entry = carry_forward_result(db_session, ctx["fy"].id, ctx["user"].id)

    acct_131 = db_session.query(Account).filter(Account.code == "131").first()
    acct_121 = db_session.query(Account).filter(Account.code == "121").first()
    lines = db_session.query(JournalLine).filter(JournalLine.entry_id == entry.id).all()

    debit_131 = [l for l in lines if l.account_id == acct_131.id][0]
    credit_121 = [l for l in lines if l.account_id == acct_121.id][0]
    assert debit_131.base_debit == Decimal("400000")
    assert credit_121.base_credit == Decimal("400000")

    with pytest.raises(ValueError) as excinfo:
        carry_forward_result(db_session, ctx["fy"].id, ctx["user"].id)
    assert "already been carried forward" in str(excinfo.value)


def test_year_close_blocked_when_earlier_periods_open(db_session, closing_context):
    ctx = closing_context
    _post(db_session, ctx, ctx["periods"][0], "Revenue", [
        JournalLineSchema(account_code=ctx["bank"].code, base_debit=Decimal("100000")),
        JournalLineSchema(account_code=ctx["revenue"].code, base_credit=Decimal("100000")),
    ])

    checklist = get_closing_checklist(db_session, ctx["fy"].id)
    assert checklist["ready"] is False

    with pytest.raises(ValueError) as excinfo:
        close_fiscal_year(db_session, ctx["fy"].id, ctx["user"].id)
    assert "cannot be closed" in str(excinfo.value)