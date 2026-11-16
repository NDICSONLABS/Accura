from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from sqlalchemy import func, select
from datetime import datetime, timezone, date
from app.models.ledger import JournalEntry, JournalLine
from app.models.master_data import AccountingJournal, JournalSequence, BudgetLine
from app.models.period import AccountingPeriod, FiscalYear
from app.models.account import Account
from app.models.audit import AuditLog
from app.models.enums import EntryStatus, BudgetEnforcementMode, PeriodStatus
from app.models.settings import OrganizationSetting
from pydantic import BaseModel, Field, field_validator
from typing import List


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


def get_next_voucher_number(db: Session, journal_code: str, fiscal_year_code: str) -> str:
    """Generates a gap-free sequential voucher number using row-level locking."""
    seq = db.execute(
        select(JournalSequence)
        .where(JournalSequence.journal_code == journal_code, JournalSequence.fiscal_year_code == fiscal_year_code)
        .with_for_update()  # ROW LOCK
    ).scalar_one_or_none()

    if not seq:
        seq = JournalSequence(journal_code=journal_code, fiscal_year_code=fiscal_year_code, current_sequence=0)
        db.add(seq)
        db.flush()

    seq.current_sequence += 1
    db.flush()

    # Format: JOURNAL-YYYY-NNNN (e.g., OD-2026-0001)
    return f"{journal_code}-{fiscal_year_code}-{seq.current_sequence:04d}"


def create_and_validate_entry(db: Session, user_id: int, data: JournalEntryCreateSchema) -> JournalEntry:
    settings = db.query(OrganizationSetting).first()
    fiscal_year = db.query(FiscalYear).filter(FiscalYear.code == data.fiscal_year_code).first()
    period = db.query(AccountingPeriod).filter(AccountingPeriod.id == data.period_id).first()
    journal = db.query(AccountingJournal).filter(AccountingJournal.code == data.journal_code).first()

    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("Cannot create entry: Accounting period is not OPEN.")
    if not fiscal_year or fiscal_year.status != "OPEN":
        raise ValueError("Cannot create entry: Fiscal year is CLOSED.")

    total_base_debit = Decimal("0")
    total_base_credit = Decimal("0")
    lines_to_create = []

    for line_data in data.lines:
        account = db.query(Account).filter(Account.code == line_data.account_code).first()
        if not account or not account.is_active or not account.is_postable:
            raise ValueError(f"Account {line_data.account_code} is invalid, inactive, or not postable.")

        # SYCEBNL Rule: Class 4 (Tiers) ALWAYS requires a third party
        if account.account_class == 4 and not line_data.third_party_id:
            raise ValueError(f"Account {account.code} (Class 4) requires a linked Third Party (Tiers).")

        # Budget Guardrail Check
        if settings.budget_control_enabled and settings.budget_enforcement_mode == BudgetEnforcementMode.STRICT:
            if line_data.budget_line_id:
                budget_line = db.query(BudgetLine).filter(BudgetLine.id == line_data.budget_line_id).first()
                if budget_line:
                    # Simplified: In production, sum all posted debits for this budget line
                    spent = db.query(func.sum(JournalLine.base_debit)).filter(
                        JournalLine.budget_line_id == budget_line.id,
                        JournalEntry.status == EntryStatus.POSTED
                    ).scalar() or Decimal("0")

                    if (spent + line_data.base_debit) > budget_line.approved_amount:
                        raise ValueError(
                            f"Budget exceeded for line. Approved: {budget_line.approved_amount}, Spent+New: {spent + line_data.base_debit}")

        total_base_debit += line_data.base_debit
        total_base_credit += line_data.base_credit

        lines_to_create.append(JournalLine(
            account_id=account.id,
            third_party_id=line_data.third_party_id,
            fund_id=line_data.fund_id if settings.donor_fund_tracking_enabled else None,
            project_id=line_data.project_id if settings.project_cost_center_enabled else None,
            budget_line_id=line_data.budget_line_id if settings.budget_control_enabled else None,
            currency_code=line_data.currency_code,
            exchange_rate=line_data.exchange_rate,
            foreign_debit=line_data.foreign_debit,
            foreign_credit=line_data.foreign_credit,
            base_debit=line_data.base_debit,
            base_credit=line_data.base_credit,
            description=line_data.description
        ))

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
        created_by_id=user_id
    )

    db.add(entry)
    db.flush()  # Get entry.id

    for line in lines_to_create:
        line.entry_id = entry.id
        db.add(line)

    # Audit Log
    db.add(AuditLog(
        user_id=user_id, entity_type="JournalEntry", entity_id=entry.id, action="CREATE",
        after_state={"voucher": voucher_number, "status": "DRAFT"}
    ))

    db.commit()
    db.refresh(entry)
    return entry


def post_journal_entry(db: Session, entry_id: int, approver_user_id: int) -> JournalEntry:
    settings = db.query(OrganizationSetting).first()
    entry = db.query(JournalEntry).filter(JournalEntry.id == entry_id).with_for_update().first()

    if not entry:
        raise ValueError("Entry not found.")
    if entry.status != EntryStatus.DRAFT and entry.status != EntryStatus.SUBMITTED:
        raise ValueError(f"Cannot post entry with status: {entry.status}")

    # Maker-Checker Enforcement
    if settings.maker_checker_approval_enabled and entry.created_by_id == approver_user_id:
        raise ValueError("Maker-Checker rule violated: Approver cannot be the same as the creator.")

    entry.status = EntryStatus.POSTED
    entry.approved_by_id = approver_user_id
    entry.posted_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=approver_user_id, entity_type="JournalEntry", entity_id=entry.id, action="POST",
        before_state={"status": entry.status.value}, after_state={"status": "POSTED"}
    ))

    db.commit()
    db.refresh(entry)
    return entry


def reverse_journal_entry(db: Session, original_entry_id: int, reverser_user_id: int,
                          reversal_date: date) -> JournalEntry:
    """Creates a Contre-passation (Reversal) entry with inverted amounts."""
    original = db.query(JournalEntry).filter(JournalEntry.id == original_entry_id).first()
    if not original or original.status != EntryStatus.POSTED:
        raise ValueError("Only POSTED entries can be reversed.")

    # Fetch original lines and invert them
    original_lines = db.query(JournalLine).filter(JournalLine.entry_id == original_entry_id).all()
    reversed_lines_data = []

    for line in original_lines:
        reversed_lines_data.append(JournalLineSchema(
            account_code=db.query(Account).filter(Account.id == line.account_id).first().code,
            third_party_id=line.third_party_id,
            fund_id=line.fund_id,
            project_id=line.project_id,
            budget_line_id=line.budget_line_id,
            currency_code=line.currency_code,
            exchange_rate=line.exchange_rate,
            foreign_debit=line.foreign_credit,  # Inverted
            foreign_credit=line.foreign_debit,  # Inverted
            base_debit=line.base_credit,  # Inverted
            base_credit=line.base_debit,  # Inverted
            description=f"Contre-passation de {original.voucher_number}"
        ))

    reversal_data = JournalEntryCreateSchema(
        journal_code=db.query(AccountingJournal).filter(AccountingJournal.id == original.journal_id).first().code,
        fiscal_year_code=db.query(FiscalYear).join(AccountingPeriod).filter(
            AccountingPeriod.id == original.period_id).first().code,
        period_id=original.period_id,  # Simplified: assumes same period or logic to find open period
        entry_date=reversal_date,
        reference=f"REV-{original.voucher_number}",
        description=f"Contre-passation (Reversal) of {original.voucher_number}",
        lines=reversed_lines_data
    )

    # Create the reversal entry (which will get a NEW sequential voucher number)
    new_entry = create_and_validate_entry(db, reverser_user_id, reversal_data)

    # Auto-post the reversal (or leave as DRAFT depending on policy; auto-post is standard for reversals)
    new_entry.status = EntryStatus.POSTED
    new_entry.approved_by_id = reverser_user_id
    new_entry.posted_at = datetime.now(timezone.utc)

    db.add(AuditLog(
        user_id=reverser_user_id, entity_type="JournalEntry", entity_id=new_entry.id, action="REVERSE",
        after_state={"reverses": original.voucher_number}
    ))

    db.commit()
    return new_entry