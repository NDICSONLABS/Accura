from sqlalchemy.orm import Session
from sqlalchemy import func, select
from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from app.models.ledger import JournalEntry, JournalLine
from app.models.account import Account
from app.models.period import AccountingPeriod, FiscalYear
from app.models.enums import EntryStatus, PeriodStatus
from app.models.master_data import ThirdParty
from app.services.ledger_service import create_and_validate_entry, JournalEntryCreateSchema, JournalLineSchema
from pydantic import BaseModel


class GLFilters(BaseModel):
    fiscal_year_id: int | None = None
    account_id: int | None = None
    third_party_id: int | None = None
    date_from: date | None = None
    date_to: date | None = None


def get_general_ledger(db: Session, filters: GLFilters):
    query = (
        select(JournalLine, JournalEntry, Account, ThirdParty)
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .join(Account, JournalLine.account_id == Account.id)
        .outerjoin(ThirdParty, JournalLine.third_party_id == ThirdParty.id)
        .where(JournalEntry.status == EntryStatus.POSTED)
    )
    if filters.fiscal_year_id:
        query = query.join(AccountingPeriod, JournalEntry.period_id == AccountingPeriod.id).where(
            AccountingPeriod.fiscal_year_id == filters.fiscal_year_id)
    if filters.account_id:
        query = query.where(JournalLine.account_id == filters.account_id)
    if filters.third_party_id:
        query = query.where(JournalLine.third_party_id == filters.third_party_id)
    if filters.date_from:
        query = query.where(JournalEntry.entry_date >= filters.date_from)
    if filters.date_to:
        query = query.where(JournalEntry.entry_date <= filters.date_to)

    return db.execute(query.order_by(JournalEntry.entry_date, JournalEntry.id, JournalLine.id)).all()


class TrialBalanceRow(BaseModel):
    account_code: str
    account_label: str
    opening_debit: Decimal
    opening_credit: Decimal
    movement_debit: Decimal
    movement_credit: Decimal
    closing_debit: Decimal
    closing_credit: Decimal


def get_trial_balance(db: Session, fiscal_year_id: int, as_of_date: date):
    fy = db.get(FiscalYear, fiscal_year_id)
    if not fy:
        return []

    # 1. Opening Balances (Cumulative before fiscal year start)
    opening_q = (
        select(
            JournalLine.account_id,
            func.sum(JournalLine.base_debit).label("d"),
            func.sum(JournalLine.base_credit).label("c")
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(JournalEntry.status == EntryStatus.POSTED, JournalEntry.entry_date < fy.start_date)
        .group_by(JournalLine.account_id)
    )
    opening_map = {r.account_id: (r.d or 0, r.c or 0) for r in db.execute(opening_q)}

    # 2. Movements within FY up to as_of_date
    movement_q = (
        select(
            JournalLine.account_id,
            func.sum(JournalLine.base_debit).label("d"),
            func.sum(JournalLine.base_credit).label("c")
        )
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(
            JournalEntry.status == EntryStatus.POSTED,
            JournalEntry.entry_date >= fy.start_date,
            JournalEntry.entry_date <= as_of_date
        )
        .group_by(JournalLine.account_id)
    )
    movement_map = {r.account_id: (r.d or 0, r.c or 0) for r in db.execute(movement_q)}

    # 3. Combine and format 6-column SYCEBNL Trial Balance
    all_ids = set(opening_map.keys()).union(set(movement_map.keys()))
    accounts = db.query(Account).filter(Account.id.in_(all_ids)).all()
    acc_map = {a.id: a for a in accounts}

    rows = []
    for acc_id in all_ids:
        acc = acc_map.get(acc_id)
        if not acc: continue

        op_d, op_c = opening_map.get(acc_id, (Decimal(0), Decimal(0)))
        net_opening = op_d - op_c
        opening_debit = net_opening if net_opening > 0 else Decimal(0)
        opening_credit = -net_opening if net_opening < 0 else Decimal(0)

        mv_d, mv_c = movement_map.get(acc_id, (Decimal(0), Decimal(0)))
        net_closing = net_opening + mv_d - mv_c
        closing_debit = net_closing if net_closing > 0 else Decimal(0)
        closing_credit = -net_closing if net_closing < 0 else Decimal(0)

        rows.append(TrialBalanceRow(
            account_code=acc.code, account_label=acc.label,
            opening_debit=opening_debit, opening_credit=opening_credit,
            movement_debit=mv_d, movement_credit=mv_c,
            closing_debit=closing_debit, closing_credit=closing_credit
        ))

    return sorted(rows, key=lambda x: x.account_code)


def close_period(db: Session, period_id: int, user_id: int):
    period = db.query(AccountingPeriod).filter(AccountingPeriod.id == period_id).with_for_update().first()
    if not period:
        raise ValueError("Period not found")
    if period.status == PeriodStatus.CLOSED:
        raise ValueError("Period is already permanently closed.")

    # Verify strict double-entry balance for the period before locking
    totals = db.execute(
        select(func.sum(JournalLine.base_debit), func.sum(JournalLine.base_credit))
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(JournalEntry.period_id == period_id, JournalEntry.status == EntryStatus.POSTED)
    ).one()

    total_d = totals[0] or Decimal(0)
    total_c = totals[1] or Decimal(0)

    if total_d != total_c:
        raise ValueError(f"Cannot close period: The ledger is unbalanced. Debit: {total_d}, Credit: {total_c}")

    period.status = PeriodStatus.CLOSED
    period.closed_by_id = user_id
    period.closed_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(period)
    return period