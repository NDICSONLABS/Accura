import calendar
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from pydantic import BaseModel, Field

from app.models.closing import FxRevaluationRun, FxRevaluationLine, FiscalYearClose
from app.models.closing import FxRevaluationRun as _Run  # noqa: F401
from app.models.account import Account
from app.models.ledger import JournalEntry, JournalLine
from app.models.period import AccountingPeriod, FiscalYear
from app.models.master_data import AccountingJournal
from app.models.enums import (
    EntryStatus, PeriodStatus, FiscalYearStatus, FxDirection,
)
from app.models.settings import OrganizationSetting
from app.services.ledger_service import (
    create_and_validate_entry, post_journal_entry, reverse_journal_entry,
    JournalEntryCreateSchema, JournalLineSchema,
)
from app.services.reporting_service import get_trial_balance, close_period

ZERO = Decimal("0")
ONE = Decimal("1")
TRANSLATION_ACCOUNTS = ("478", "479")
MONETARY_CLASSES = (1, 4, 5)


def _q0(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def _q2(v: Decimal) -> Decimal:
    return v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class FxRateSchema(BaseModel):
    currency_code: str
    closing_rate: Decimal = Field(max_digits=18, decimal_places=6)


class FxRevaluationSchema(BaseModel):
    period_id: int
    rates: list[FxRateSchema]
    provision_expense_account_code: str | None = None
    provision_account_code: str | None = None


# ------------------------------------------------------------------ PERIOD LOCKS


def soft_lock_period(db: Session, period_id: int, user_id: int) -> AccountingPeriod:
    period = db.get(AccountingPeriod, period_id)
    if not period:
        raise ValueError("Period not found")
    if period.status == PeriodStatus.CLOSED:
        raise ValueError("Period is already permanently closed.")
    if period.status == PeriodStatus.SOFT_LOCKED:
        return period

    period.status = PeriodStatus.SOFT_LOCKED
    period.closed_by_id = user_id
    period.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(period)
    return period


# ------------------------------------------------------------------ FX EXPOSURES


def get_fx_exposures(db: Session, as_of_date: date) -> list[dict]:
    """Open foreign-currency monetary balances, grouped by account / tiers / currency."""
    query = (
        select(
            JournalLine.account_id,
            JournalLine.third_party_id,
            JournalLine.currency_code,
            func.sum(JournalLine.foreign_debit - JournalLine.foreign_credit).label("net_foreign"),
            func.sum(JournalLine.base_debit - JournalLine.base_credit).label("net_base"),
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .where(
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.entry_date <= as_of_date,
            JournalLine.currency_code != "XAF",
            Account.account_class.in_(MONETARY_CLASSES),
            Account.code.notin_(TRANSLATION_ACCOUNTS),
        )
        .group_by(JournalLine.account_id, JournalLine.third_party_id, JournalLine.currency_code)
    )

    exposures = []
    for row in db.execute(query).all():
        net_foreign = Decimal(row.net_foreign or ZERO)
        if net_foreign == ZERO:
            continue
        account = db.get(Account, row.account_id)
        exposures.append({
            "account_id": row.account_id,
            "account_code": account.code,
            "account_label": account.label,
            "requires_third_party": account.requires_third_party,
            "third_party_id": row.third_party_id,
            "currency_code": row.currency_code,
            "foreign_balance": _q2(net_foreign),
            "historical_base": _q0(Decimal(row.net_base or ZERO)),
        })

    return sorted(exposures, key=lambda e: (e["account_code"], e["currency_code"]))


def preview_fx_revaluation(db: Session, as_of_date: date, rates: dict[str, Decimal]) -> list[dict]:
    rows = []
    for exposure in get_fx_exposures(db, as_of_date):
        rate = rates.get(exposure["currency_code"])
        if not rate or rate <= ZERO:
            continue
        revalued = _q0(exposure["foreign_balance"] * rate)
        difference = revalued - exposure["historical_base"]
        if difference == ZERO:
            continue
        rows.append({
            **exposure,
            "closing_rate": rate,
            "revalued_base": revalued,
            "difference_base": difference,
            "direction": FxDirection.GAIN if difference > ZERO else FxDirection.LOSS,
        })
    return rows


# ------------------------------------------------------------------ FX REVALUATION


def create_fx_revaluation(db: Session, user_id: int, data: FxRevaluationSchema) -> FxRevaluationRun:
    settings = db.query(OrganizationSetting).first()
    if not (settings and settings.multi_currency_enabled):
        raise ValueError("Multi-currency is not enabled in organization settings.")

    period = db.get(AccountingPeriod, data.period_id)
    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("Revaluation period must be OPEN.")

    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)
    if not fiscal_year or fiscal_year.status != FiscalYearStatus.OPEN:
        raise ValueError("Fiscal year is not OPEN.")

    unreversed = (
        db.query(FxRevaluationRun)
        .filter(
            FxRevaluationRun.fiscal_year_id == fiscal_year.id,
            FxRevaluationRun.status == EntryStatus.POSTED,
            FxRevaluationRun.reversal_entry_id.is_(None),
        )
        .first()
    )
    if unreversed:
        raise ValueError("A previous FX revaluation must be reversed before running a new one.")

    if not data.rates:
        raise ValueError("At least one closing rate is required.")

    rates = {r.currency_code: r.closing_rate for r in data.rates}
    for code, rate in rates.items():
        if rate <= ZERO:
            raise ValueError("Exchange rate must be greater than zero.")

    preview = preview_fx_revaluation(db, period.end_date, rates)
    if not preview:
        raise ValueError("No foreign currency exposure requires revaluation at these rates.")

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "CLOT").first()
    if not journal:
        raise ValueError("Closing journal 'CLOT' is missing. Run migrations.")

    loss_account = db.query(Account).filter(Account.code == "478").first()
    gain_account = db.query(Account).filter(Account.code == "479").first()
    if not loss_account or not gain_account:
        raise ValueError("Translation accounts 478 / 479 are missing. Run migrations.")

    provision_expense = None
    provision_account = None
    if data.provision_expense_account_code or data.provision_account_code:
        if not (data.provision_expense_account_code and data.provision_account_code):
            raise ValueError("Provisioning requires both an expense account and a provision account.")
        provision_expense = db.query(Account).filter(Account.code == data.provision_expense_account_code).first()
        provision_account = db.query(Account).filter(Account.code == data.provision_account_code).first()
        if not provision_expense or provision_expense.account_class != 6 or not provision_expense.is_postable:
            raise ValueError("Provision expense account must be a postable Class 6 account.")
        if not provision_account or provision_account.account_class != 1 or not provision_account.is_postable:
            raise ValueError("Provision account must be a postable Class 1 account.")

    run = FxRevaluationRun(
        fiscal_year_id=fiscal_year.id,
        period_id=period.id,
        as_of_date=period.end_date,
        status=EntryStatus.DRAFT,
        provision_expense_account_id=provision_expense.id if provision_expense else None,
        provision_account_id=provision_account.id if provision_account else None,
        created_by_id=user_id,
    )
    db.add(run)
    db.flush()

    total_loss = ZERO
    total_gain = ZERO
    lines: list[JournalLineSchema] = []

    for row in preview:
        difference = row["difference_base"]
        magnitude = abs(difference)

        db.add(FxRevaluationLine(
            run_id=run.id,
            account_id=row["account_id"],
            third_party_id=row["third_party_id"],
            currency_code=row["currency_code"],
            foreign_balance=row["foreign_balance"],
            historical_base=row["historical_base"],
            closing_rate=row["closing_rate"],
            revalued_base=row["revalued_base"],
            difference_base=difference,
            direction=row["direction"],
        ))

        tiers = row["third_party_id"] if row["requires_third_party"] else None

        if difference > ZERO:
            total_gain += magnitude
            lines.append(JournalLineSchema(
                account_code=row["account_code"], third_party_id=tiers,
                currency_code=row["currency_code"], exchange_rate=row["closing_rate"],
                base_debit=magnitude,
                description=f"Écart de conversion — {row['currency_code']}",
            ))
        else:
            total_loss += magnitude
            lines.append(JournalLineSchema(
                account_code=row["account_code"], third_party_id=tiers,
                currency_code=row["currency_code"], exchange_rate=row["closing_rate"],
                base_credit=magnitude,
                description=f"Écart de conversion — {row['currency_code']}",
            ))

    if total_loss > ZERO:
        lines.append(JournalLineSchema(
            account_code=loss_account.code, currency_code="XAF", exchange_rate=ONE,
            base_debit=total_loss, description="Écart de conversion — Actif (perte latente)",
        ))
    if total_gain > ZERO:
        lines.append(JournalLineSchema(
            account_code=gain_account.code, currency_code="XAF", exchange_rate=ONE,
            base_credit=total_gain, description="Écart de conversion — Passif (gain latent)",
        ))

    entry_data = JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=period.end_date,
        reference=f"FX-{fiscal_year.code}-{period.period_number:02d}",
        description=f"Réévaluation des écarts de conversion au {period.end_date.isoformat()}",
        lines=lines,
    )

    entry = create_and_validate_entry(db, user_id, entry_data)
    posted = post_journal_entry(db, entry.id, user_id)

    run.status = EntryStatus.POSTED
    run.journal_entry_id = posted.id
    run.total_latent_loss_base = total_loss
    run.total_latent_gain_base = total_gain

    if total_loss > ZERO and provision_expense and provision_account:
        provision_lines = [
            JournalLineSchema(
                account_code=provision_expense.code, currency_code="XAF", exchange_rate=ONE,
                base_debit=total_loss, description="Dotation pour perte de change latente",
            ),
            JournalLineSchema(
                account_code=provision_account.code, currency_code="XAF", exchange_rate=ONE,
                base_credit=total_loss, description="Provision pour perte de change latente",
            ),
        ]
        provision_entry = create_and_validate_entry(db, user_id, JournalEntryCreateSchema(
            journal_code=journal.code,
            fiscal_year_code=fiscal_year.code,
            period_id=period.id,
            entry_date=period.end_date,
            reference=f"FXPROV-{fiscal_year.code}-{period.period_number:02d}",
            description="Provision pour perte de change latente",
            lines=provision_lines,
        ))
        provision_posted = post_journal_entry(db, provision_entry.id, user_id)
        run.provision_entry_id = provision_posted.id

    db.commit()
    db.refresh(run)
    return run


def reverse_fx_revaluation(db: Session, run_id: int, user_id: int, reversal_date: date) -> FxRevaluationRun:
    run = db.get(FxRevaluationRun, run_id)
    if not run:
        raise ValueError("Revaluation run not found.")
    if run.status != EntryStatus.POSTED:
        raise ValueError("Only POSTED revaluations can be reversed.")
    if run.reversal_entry_id:
        raise ValueError("This revaluation has already been reversed.")

    reversal = reverse_journal_entry(db, run.journal_entry_id, user_id, reversal_date)
    run.reversal_entry_id = reversal.id

    if run.provision_entry_id:
        reverse_journal_entry(db, run.provision_entry_id, user_id, reversal_date)

    db.commit()
    db.refresh(run)
    return run


def get_revaluation_detail(db: Session, run_id: int) -> dict | None:
    run = db.get(FxRevaluationRun, run_id)
    if not run:
        return None
    lines = (
        db.query(FxRevaluationLine, Account)
        .join(Account, FxRevaluationLine.account_id == Account.id)
        .filter(FxRevaluationLine.run_id == run_id)
        .order_by(Account.code)
        .all()
    )
    return {
        "run": run,
        "lines": lines,
        "period": db.get(AccountingPeriod, run.period_id),
        "fiscal_year": db.get(FiscalYear, run.fiscal_year_id),
        "unprovisioned_loss": (
            run.total_latent_loss_base > ZERO and run.provision_entry_id is None
        ),
    }


# ------------------------------------------------------------------ YEAR CLOSE


def _management_balances(db: Session, fiscal_year_id: int) -> list[dict]:
    query = (
        select(
            Account.id, Account.code, Account.label, Account.account_class,
            func.sum(JournalLine.base_debit - JournalLine.base_credit).label("net"),
        )
        .join(JournalLine, JournalLine.account_id == Account.id)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(AccountingPeriod, JournalEntry.period_id == AccountingPeriod.id)
        .where(
            JournalEntry.status == EntryStatus.POSTED,
            AccountingPeriod.fiscal_year_id == fiscal_year_id,
            Account.account_class.in_([6, 7]),
        )
        .group_by(Account.id, Account.code, Account.label, Account.account_class)
        .order_by(Account.code)
    )
    rows = []
    for row in db.execute(query).all():
        net = _q0(Decimal(row.net or ZERO))
        if net != ZERO:
            rows.append({
                "account_id": row.id, "code": row.code, "label": row.label,
                "account_class": row.account_class, "net": net,
            })
    return rows


def get_closing_checklist(db: Session, fiscal_year_id: int) -> dict:
    fiscal_year = db.get(FiscalYear, fiscal_year_id)
    if not fiscal_year:
        raise ValueError("Fiscal year not found.")

    periods = (
        db.query(AccountingPeriod)
        .filter(AccountingPeriod.fiscal_year_id == fiscal_year_id)
        .order_by(AccountingPeriod.period_number)
        .all()
    )
    if not periods:
        raise ValueError("Fiscal year has no accounting periods.")

    last_period = periods[-1]
    earlier = periods[:-1]

    trial_balance = get_trial_balance(db, fiscal_year_id, fiscal_year.end_date)
    total_debit = sum((r.closing_debit for r in trial_balance), ZERO)
    total_credit = sum((r.closing_credit for r in trial_balance), ZERO)
    balanced = total_debit == total_credit

    management = _management_balances(db, fiscal_year_id)
    result = -sum((r["net"] for r in management), ZERO)

    existing_close = (
        db.query(FiscalYearClose)
        .filter(FiscalYearClose.fiscal_year_id == fiscal_year_id)
        .first()
    )
    unreversed = (
        db.query(FxRevaluationRun)
        .filter(
            FxRevaluationRun.fiscal_year_id == fiscal_year_id,
            FxRevaluationRun.status == EntryStatus.POSTED,
            FxRevaluationRun.reversal_entry_id.is_(None),
        )
        .count()
    )

    blockers: list[str] = []
    if fiscal_year.status == FiscalYearStatus.CLOSED:
        blockers.append("Fiscal year is already CLOSED.")
    if any(p.status == PeriodStatus.OPEN for p in earlier):
        blockers.append("All periods except the last must be soft-locked or closed.")
    if last_period.status != PeriodStatus.OPEN:
        blockers.append("The last period must be OPEN to receive the result entry.")
    if not balanced:
        blockers.append("Trial balance is not balanced.")

    return {
        "fiscal_year": fiscal_year,
        "periods": periods,
        "last_period": last_period,
        "balanced": balanced,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "management_balances": management,
        "result": result,
        "blockers": blockers,
        "ready": len(blockers) == 0,
        "existing_close": existing_close,
        "unreversed_revaluations": unreversed,
    }


def close_fiscal_year(db: Session, fiscal_year_id: int, user_id: int) -> FiscalYearClose:
    checklist = get_closing_checklist(db, fiscal_year_id)
    if checklist["existing_close"]:
        raise ValueError("Fiscal year is already closed.")
    if not checklist["ready"]:
        raise ValueError("Fiscal year cannot be closed: " + " ".join(checklist["blockers"]))

    fiscal_year = checklist["fiscal_year"]
    last_period = checklist["last_period"]
    result = checklist["result"]

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "CLOT").first()
    if not journal:
        raise ValueError("Closing journal 'CLOT' is missing. Run migrations.")

    result_account = db.query(Account).filter(Account.code == "131").first()
    if not result_account or not result_account.is_postable:
        raise ValueError("Result account 131 must be postable. Run migrations.")

    lines: list[JournalLineSchema] = []
    for row in checklist["management_balances"]:
        net = row["net"]
        if net > ZERO:
            lines.append(JournalLineSchema(
                account_code=row["code"], currency_code="XAF", exchange_rate=ONE,
                base_credit=net, description="Solde des comptes de gestion",
            ))
        else:
            lines.append(JournalLineSchema(
                account_code=row["code"], currency_code="XAF", exchange_rate=ONE,
                base_debit=-net, description="Solde des comptes de gestion",
            ))

    if result > ZERO:
        lines.append(JournalLineSchema(
            account_code=result_account.code, currency_code="XAF", exchange_rate=ONE,
            base_credit=result, description="Résultat net de l'exercice (bénéfice)",
        ))
    elif result < ZERO:
        lines.append(JournalLineSchema(
            account_code=result_account.code, currency_code="XAF", exchange_rate=ONE,
            base_debit=-result, description="Résultat net de l'exercice (perte)",
        ))

    if not lines:
        raise ValueError("No management balances to close for this fiscal year.")

    entry = create_and_validate_entry(db, user_id, JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=fiscal_year.code,
        period_id=last_period.id,
        entry_date=last_period.end_date,
        reference=f"RESULT-{fiscal_year.code}",
        description=f"Détermination du résultat {fiscal_year.code}",
        lines=lines,
    ))
    posted = post_journal_entry(db, entry.id, user_id)

    close_period(db, last_period.id, user_id)

    fiscal_year.status = FiscalYearStatus.CLOSED

    record = FiscalYearClose(
        fiscal_year_id=fiscal_year.id,
        result_base=result,
        result_entry_id=posted.id,
        closed_by_id=user_id,
        closed_at=datetime.now(timezone.utc),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def open_next_fiscal_year(db: Session, fiscal_year_id: int) -> FiscalYear:
    fiscal_year = db.get(FiscalYear, fiscal_year_id)
    if not fiscal_year:
        raise ValueError("Fiscal year not found.")
    try:
        next_code = str(int(fiscal_year.code) + 1)
    except ValueError:
        raise ValueError("Fiscal year code must be numeric to derive the next year.")

    existing = db.query(FiscalYear).filter(FiscalYear.code == next_code).first()
    if existing:
        return existing

    year = int(next_code)
    next_fy = FiscalYear(
        code=next_code,
        start_date=date(year, 1, 1),
        end_date=date(year, 12, 31),
        status=FiscalYearStatus.OPEN,
    )
    db.add(next_fy)
    db.flush()

    for month in range(1, 13):
        last_day = calendar.monthrange(year, month)[1]
        db.add(AccountingPeriod(
            fiscal_year_id=next_fy.id,
            period_number=month,
            start_date=date(year, month, 1),
            end_date=date(year, month, last_day),
            status=PeriodStatus.OPEN,
        ))

    record = (
        db.query(FiscalYearClose)
        .filter(FiscalYearClose.fiscal_year_id == fiscal_year_id)
        .first()
    )
    if record:
        record.next_fiscal_year_id = next_fy.id

    db.commit()
    db.refresh(next_fy)
    return next_fy


def carry_forward_result(db: Session, fiscal_year_id: int, user_id: int) -> JournalEntry:
    record = (
        db.query(FiscalYearClose)
        .filter(FiscalYearClose.fiscal_year_id == fiscal_year_id)
        .first()
    )
    if not record:
        raise ValueError("Fiscal year has not been closed yet.")
    if record.carry_forward_entry_id:
        raise ValueError("Result has already been carried forward.")
    if not record.next_fiscal_year_id:
        raise ValueError("Open the next fiscal year before carrying forward the result.")

    next_fy = db.get(FiscalYear, record.next_fiscal_year_id)
    first_period = (
        db.query(AccountingPeriod)
        .filter(
            AccountingPeriod.fiscal_year_id == next_fy.id,
            AccountingPeriod.status == PeriodStatus.OPEN,
        )
        .order_by(AccountingPeriod.period_number)
        .first()
    )
    if not first_period:
        raise ValueError("The next fiscal year has no OPEN period.")

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "CLOT").first()
    result_account = db.query(Account).filter(Account.code == "131").first()
    retained_account = db.query(Account).filter(Account.code == "121").first()
    if not retained_account or not retained_account.is_postable:
        raise ValueError("Retained earnings account 121 must be postable. Run migrations.")

    result = Decimal(record.result_base)
    if result == ZERO:
        raise ValueError("Result is zero; nothing to carry forward.")

    if result > ZERO:
        lines = [
            JournalLineSchema(account_code=result_account.code, currency_code="XAF",
                              exchange_rate=ONE, base_debit=result,
                              description="Affectation du résultat"),
            JournalLineSchema(account_code=retained_account.code, currency_code="XAF",
                              exchange_rate=ONE, base_credit=result,
                              description="Report à nouveau (bénéfice)"),
        ]
    else:
        lines = [
            JournalLineSchema(account_code=retained_account.code, currency_code="XAF",
                              exchange_rate=ONE, base_debit=-result,
                              description="Report à nouveau (perte)"),
            JournalLineSchema(account_code=result_account.code, currency_code="XAF",
                              exchange_rate=ONE, base_credit=-result,
                              description="Affectation du résultat"),
        ]

    entry = create_and_validate_entry(db, user_id, JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=next_fy.code,
        period_id=first_period.id,
        entry_date=first_period.start_date,
        reference=f"ANOU-{next_fy.code}",
        description=f"Affectation du résultat {record.fiscal_year_id}",
        lines=lines,
    ))
    posted = post_journal_entry(db, entry.id, user_id)

    record.carry_forward_entry_id = posted.id
    db.commit()
    db.refresh(posted)
    return posted