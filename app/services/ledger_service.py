from decimal import Decimal, ROUND_HALF_UP
from datetime import datetime, timezone, date
from typing import List

from sqlalchemy.orm import Session
from sqlalchemy import func, select, or_
from pydantic import BaseModel, Field

from app.models.ledger import JournalEntry, JournalLine
from app.models.master_data import AccountingJournal, JournalSequence, BudgetLine, ThirdParty
from app.models.period import AccountingPeriod, FiscalYear
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.user import User
from app.models.enums import (
    EntryStatus,
    BudgetEnforcementMode,
    PeriodStatus,
    FiscalYearStatus,
)
from app.models.settings import OrganizationSetting


class JournalLineSchema(BaseModel):
    account_code: str
    third_party_id: int | None = None
    fund_id: int | None = None
    project_id: int | None = None
    budget_line_id: int | None = None
    currency_code: str = "XAF"
    exchange_rate: Decimal = Field(default=Decimal("1.000000"), max_digits=18, decimal_places=6)
    foreign_debit: Decimal = Field(default=Decimal("0.00"), max_digits=18, decimal_places=2)
    foreign_credit: Decimal = Field(default=Decimal("0.00"), max_digits=18, decimal_places=2)
    base_debit: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=0)
    base_credit: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=0)
    description: str | None = None


class JournalEntryCreateSchema(BaseModel):
    journal_code: str
    fiscal_year_code: str
    period_id: int
    entry_date: date
    reference: str | None = None
    description: str
    lines: List[JournalLineSchema]


class JournalListFilters(BaseModel):
    fiscal_year_id: int | None = None
    journal_id: int | None = None
    status: EntryStatus | None = None
    date_from: date | None = None
    date_to: date | None = None
    search: str | None = None


def get_next_voucher_number(db: Session, journal_code: str, fiscal_year_code: str) -> str:
    """Gap-free sequential voucher numbering with row-level locking."""
    seq = db.execute(
        select(JournalSequence)
        .where(
            JournalSequence.journal_code == journal_code,
            JournalSequence.fiscal_year_code == fiscal_year_code,
        )
        .with_for_update()
    ).scalar_one_or_none()

    if not seq:
        seq = JournalSequence(
            journal_code=journal_code,
            fiscal_year_code=fiscal_year_code,
            current_sequence=0,
        )
        db.add(seq)
        db.flush()

    seq.current_sequence += 1
    db.flush()

    return f"{journal_code}-{fiscal_year_code}-{seq.current_sequence:04d}"


def create_and_validate_entry(
    db: Session,
    user_id: int,
    data: JournalEntryCreateSchema,
) -> JournalEntry:
    settings = db.query(OrganizationSetting).first()
    fiscal_year = db.query(FiscalYear).filter(FiscalYear.code == data.fiscal_year_code).first()
    period = db.get(AccountingPeriod, data.period_id)
    journal = db.query(AccountingJournal).filter(AccountingJournal.code == data.journal_code).first()

    if not journal:
        raise ValueError(f"Journal '{data.journal_code}' does not exist.")
    if not fiscal_year or fiscal_year.status != FiscalYearStatus.OPEN:
        raise ValueError("Cannot create entry: Fiscal year is not OPEN.")
    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("Cannot create entry: Accounting period is not OPEN.")
    if period.fiscal_year_id != fiscal_year.id:
        raise ValueError("Selected period does not belong to the selected fiscal year.")
    if not (period.start_date <= data.entry_date <= period.end_date):
        raise ValueError("Entry date falls outside the selected accounting period.")

    total_base_debit = Decimal("0")
    total_base_credit = Decimal("0")
    lines_to_create: list[JournalLine] = []

    for line_data in data.lines:
        account = db.query(Account).filter(Account.code == line_data.account_code).first()

        if not account or not account.is_active or not account.is_postable:
            raise ValueError(f"Account {line_data.account_code} is invalid, inactive, or not postable.")

        if account.account_class == 4 and not line_data.third_party_id:
            raise ValueError(f"Account {account.code} (Class 4) requires a linked Third Party (Tiers).")

        if line_data.base_debit > 0 and line_data.base_credit > 0:
            raise ValueError("A journal line cannot carry both a debit and a credit.")

        # FIXED: explicit join prevents cartesian product in budget consumption sum.
        if (
            settings
            and settings.budget_control_enabled
            and settings.budget_enforcement_mode == BudgetEnforcementMode.STRICT
            and line_data.budget_line_id
        ):
            budget_line = db.get(BudgetLine, line_data.budget_line_id)
            if budget_line:
                spent = db.execute(
                    select(func.coalesce(func.sum(JournalLine.base_debit), 0))
                    .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
                    .where(
                        JournalLine.budget_line_id == budget_line.id,
                        JournalEntry.status == EntryStatus.POSTED,
                    )
                ).scalar()
                spent = Decimal(spent) if spent else Decimal("0")

                if (spent + line_data.base_debit) > Decimal(budget_line.approved_amount):
                    raise ValueError(
                        f"Budget exceeded for account {account.code}. "
                        f"Approved: {budget_line.approved_amount}, "
                        f"Spent + New: {spent + line_data.base_debit}"
                    )

        total_base_debit += line_data.base_debit
        total_base_credit += line_data.base_credit

        lines_to_create.append(
            JournalLine(
                account_id=account.id,
                third_party_id=line_data.third_party_id,
                fund_id=line_data.fund_id if settings and settings.donor_fund_tracking_enabled else None,
                project_id=line_data.project_id if settings and settings.project_cost_center_enabled else None,
                budget_line_id=line_data.budget_line_id if settings and settings.budget_control_enabled else None,
                currency_code=line_data.currency_code,
                exchange_rate=line_data.exchange_rate,
                foreign_debit=line_data.foreign_debit,
                foreign_credit=line_data.foreign_credit,
                base_debit=line_data.base_debit,
                base_credit=line_data.base_credit,
                description=line_data.description,
            )
        )

    if not lines_to_create:
        raise ValueError("At least one journal line is required.")
    if total_base_debit != total_base_credit:
        raise ValueError(f"Entry is unbalanced. Debit: {total_base_debit}, Credit: {total_base_credit}")
    if total_base_debit == Decimal("0"):
        raise ValueError("Entry cannot be zero.")

    voucher_number = get_next_voucher_number(db, data.journal_code, data.fiscal_year_code)

    entry = JournalEntry(
        journal_id=journal.id,
        period_id=period.id,
        entry_date=data.entry_date,
        voucher_number=voucher_number,
        reference=data.reference,
        description=data.description,
        status=EntryStatus.DRAFT,
        created_by_id=user_id,
    )

    db.add(entry)
    db.flush()

    for line in lines_to_create:
        line.entry_id = entry.id
        db.add(line)

    db.add(
        AuditLog(
            user_id=user_id,
            entity_type="JournalEntry",
            entity_id=entry.id,
            action="CREATE",
            after_state={"voucher": voucher_number, "status": "DRAFT"},
        )
    )

    db.commit()
    db.refresh(entry)
    return entry


def post_journal_entry(db: Session, entry_id: int, approver_user_id: int) -> JournalEntry:
    settings = db.query(OrganizationSetting).first()
    entry = (
        db.query(JournalEntry)
        .filter(JournalEntry.id == entry_id)
        .with_for_update()
        .first()
    )

    if not entry:
        raise ValueError("Entry not found.")
    if entry.status not in (EntryStatus.DRAFT, EntryStatus.SUBMITTED):
        raise ValueError(f"Cannot post entry with status: {entry.status.value}")

    period = db.get(AccountingPeriod, entry.period_id)
    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("Cannot post entry: Accounting period is not OPEN.")

    if (
        settings
        and settings.maker_checker_approval_enabled
        and entry.created_by_id == approver_user_id
    ):
        raise ValueError("Maker-Checker rule violated: Approver cannot be the same as the creator.")

    # FIXED: capture the state BEFORE mutation so the audit trail is truthful.
    before_status = entry.status.value

    entry.status = EntryStatus.POSTED
    entry.approved_by_id = approver_user_id
    entry.posted_at = datetime.now(timezone.utc)

    db.add(
        AuditLog(
            user_id=approver_user_id,
            entity_type="JournalEntry",
            entity_id=entry.id,
            action="POST",
            before_state={"status": before_status},
            after_state={"status": "POSTED"},
        )
    )

    db.commit()
    db.refresh(entry)
    return entry


def reverse_journal_entry(
    db: Session,
    original_entry_id: int,
    reverser_user_id: int,
    reversal_date: date,
    target_period_id: int | None = None,
) -> JournalEntry:
    """
    Contre-passation: creates a new POSTED entry with inverted debit/credit amounts.
    FIXED: resolves an OPEN period for the reversal date instead of reusing a locked period.
    """
    original = db.get(JournalEntry, original_entry_id)
    if not original or original.status != EntryStatus.POSTED:
        raise ValueError("Only POSTED entries can be reversed.")

    if target_period_id:
        period = db.get(AccountingPeriod, target_period_id)
    else:
        period = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.start_date <= reversal_date,
                AccountingPeriod.end_date >= reversal_date,
                AccountingPeriod.status == PeriodStatus.OPEN,
            )
            .order_by(AccountingPeriod.start_date)
            .first()
        )

    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("No OPEN accounting period is available for the reversal date.")

    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)
    journal = db.get(AccountingJournal, original.journal_id)

    if not fiscal_year or fiscal_year.status != FiscalYearStatus.OPEN:
        raise ValueError("Cannot reverse: target fiscal year is not OPEN.")
    if not journal:
        raise ValueError("Original journal not found.")

    original_lines = (
        db.query(JournalLine).filter(JournalLine.entry_id == original_entry_id).all()
    )

    reversed_lines: list[JournalLineSchema] = []
    for line in original_lines:
        account = db.get(Account, line.account_id)
        reversed_lines.append(
            JournalLineSchema(
                account_code=account.code,
                third_party_id=line.third_party_id,
                fund_id=line.fund_id,
                project_id=line.project_id,
                budget_line_id=line.budget_line_id,
                currency_code=line.currency_code,
                exchange_rate=line.exchange_rate,
                foreign_debit=line.foreign_credit,
                foreign_credit=line.foreign_debit,
                base_debit=line.base_credit,
                base_credit=line.base_debit,
                description=f"Contre-passation {original.voucher_number}",
            )
        )

    reversal_data = JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=reversal_date,
        reference=f"REV-{original.voucher_number}",
        description=f"Contre-passation de {original.voucher_number}",
        lines=reversed_lines,
    )

    new_entry = create_and_validate_entry(db, reverser_user_id, reversal_data)

    new_entry.status = EntryStatus.POSTED
    new_entry.approved_by_id = reverser_user_id
    new_entry.posted_at = datetime.now(timezone.utc)

    db.add(
        AuditLog(
            user_id=reverser_user_id,
            entity_type="JournalEntry",
            entity_id=new_entry.id,
            action="REVERSE",
            before_state={"reverses": original.voucher_number},
            after_state={"voucher": new_entry.voucher_number, "status": "POSTED"},
        )
    )

    db.commit()
    db.refresh(new_entry)
    return new_entry


def list_journal_entries(db: Session, filters: JournalListFilters):
    query = (
        select(JournalEntry, AccountingJournal, AccountingPeriod, User)
        .join(AccountingJournal, JournalEntry.journal_id == AccountingJournal.id)
        .join(AccountingPeriod, JournalEntry.period_id == AccountingPeriod.id)
        .join(User, JournalEntry.created_by_id == User.id)
    )

    if filters.fiscal_year_id:
        query = query.where(AccountingPeriod.fiscal_year_id == filters.fiscal_year_id)
    if filters.journal_id:
        query = query.where(JournalEntry.journal_id == filters.journal_id)
    if filters.status:
        query = query.where(JournalEntry.status == filters.status)
    if filters.date_from:
        query = query.where(JournalEntry.entry_date >= filters.date_from)
    if filters.date_to:
        query = query.where(JournalEntry.entry_date <= filters.date_to)
    if filters.search:
        pattern = f"%{filters.search}%"
        query = query.where(
            or_(
                JournalEntry.voucher_number.ilike(pattern),
                JournalEntry.description.ilike(pattern),
                JournalEntry.reference.ilike(pattern),
            )
        )

    query = query.order_by(JournalEntry.entry_date.desc(), JournalEntry.id.desc()).limit(200)
    return db.execute(query).all()


def get_journal_entry_detail(db: Session, entry_id: int) -> dict | None:
    entry = db.get(JournalEntry, entry_id)
    if not entry:
        return None

    journal = db.get(AccountingJournal, entry.journal_id)
    period = db.get(AccountingPeriod, entry.period_id)
    fiscal_year = db.get(FiscalYear, period.fiscal_year_id) if period else None
    creator = db.get(User, entry.created_by_id)
    approver = db.get(User, entry.approved_by_id) if entry.approved_by_id else None

    lines = db.execute(
        select(JournalLine, Account, ThirdParty)
        .join(Account, JournalLine.account_id == Account.id)
        .outerjoin(ThirdParty, JournalLine.third_party_id == ThirdParty.id)
        .where(JournalLine.entry_id == entry_id)
        .order_by(JournalLine.id)
    ).all()

    total_debit = sum((line.base_debit for line, _, _ in lines), Decimal("0"))
    total_credit = sum((line.base_credit for line, _, _ in lines), Decimal("0"))

    return {
        "entry": entry,
        "journal": journal,
        "period": period,
        "fiscal_year": fiscal_year,
        "creator": creator,
        "approver": approver,
        "lines": lines,
        "total_debit": total_debit,
        "total_credit": total_credit,
        "difference": total_debit - total_credit,
    }