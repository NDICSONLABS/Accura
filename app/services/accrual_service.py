from decimal import Decimal, ROUND_HALF_UP
from sqlalchemy.orm import Session
from datetime import date, datetime, timezone
from app.models.accruals import SupplierBill, SupplierBillLine, TreasurySettlement, SettlementAllocation
from app.models.ledger import JournalEntry, JournalLine
from app.models.master_data import AccountingJournal
from app.models.account import Account
from app.models.enums import EntryStatus
from app.models.settings import OrganizationSetting
from app.services.ledger_service import get_next_voucher_number
from pydantic import BaseModel, Field
from typing import List


class BillLineSchema(BaseModel):
    account_code: str
    base_amount: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=0)
    foreign_amount: Decimal = Field(default=Decimal("0.00"), max_digits=18, decimal_places=2)
    project_id: int | None = None
    fund_id: int | None = None
    budget_line_id: int | None = None
    description: str | None = None


class SupplierBillCreateSchema(BaseModel):
    third_party_id: int
    bill_date: date
    due_date: date
    reference: str
    description: str
    currency_code: str = "XAF"
    exchange_rate: Decimal = Field(default=Decimal("1.000000"), max_digits=18, decimal_places=6)
    withholding_tax_base: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=0)
    lines: List[BillLineSchema]


def create_supplier_bill(db: Session, user_id: int, data: SupplierBillCreateSchema) -> SupplierBill:
    settings = db.query(OrganizationSetting).first()

    # Validate withholding tax rule
    if data.withholding_tax_base > 0 and not settings.tax_withholding_enabled:
        raise ValueError("Withholding tax is not enabled in organization settings.")

    bill = SupplierBill(
        third_party_id=data.third_party_id,
        bill_date=data.bill_date,
        due_date=data.due_date,
        reference=data.reference,
        description=data.description,
        currency_code=data.currency_code,
        exchange_rate=data.exchange_rate,
        withholding_tax_base=data.withholding_tax_base,
        status=EntryStatus.DRAFT,
        created_by_id=user_id
    )
    db.add(bill)
    db.flush()

    for line_data in data.lines:
        account = db.query(Account).filter(Account.code == line_data.account_code).first()
        if not account or not account.is_postable:
            raise ValueError(f"Account {line_data.account_code} is invalid or not postable.")

        line = SupplierBillLine(
            bill_id=bill.id,
            account_id=account.id,
            project_id=line_data.project_id if settings.project_cost_center_enabled else None,
            fund_id=line_data.fund_id if settings.donor_fund_tracking_enabled else None,
            budget_line_id=line_data.budget_line_id if settings.budget_control_enabled else None,
            description=line_data.description,
            base_amount=line_data.base_amount,
            foreign_amount=line_data.foreign_amount
        )
        db.add(line)

    db.commit()
    db.refresh(bill)
    return bill


def post_supplier_bill(db: Session, bill_id: int, approver_id: int) -> SupplierBill:
    bill = db.query(SupplierBill).filter(SupplierBill.id == bill_id).with_for_update().first()
    if not bill or bill.status != EntryStatus.DRAFT:
        raise ValueError("Bill must be in DRAFT status to post.")

    settings = db.query(OrganizationSetting).first()
    lines = db.query(SupplierBillLine).filter(SupplierBillLine.bill_id == bill_id).all()
    third_party = db.query(Account).join(SupplierBill).filter(
        SupplierBill.id == bill_id).first()  # Simplified: get account from third_party

    total_base = sum(line.base_amount for line in lines)
    net_payable_base = total_base - bill.withholding_tax_base

    if net_payable_base < 0:
        raise ValueError("Withholding tax cannot exceed total bill amount.")

    # 1. Create Journal Entry
    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "ACH").first()
    voucher = get_next_voucher_number(db, "ACH", "2026")  # Simplified FY lookup

    entry = JournalEntry(
        journal_id=journal.id,
        period_id=bill.created_by_id,  # Placeholder: should link to actual open period
        entry_date=bill.bill_date,
        voucher_number=voucher,
        reference=bill.reference,
        description=f"Facture Fournisseur: {bill.description}",
        status=EntryStatus.POSTED,
        created_by_id=bill.created_by_id,
        approved_by_id=approver_id,
        posted_at=datetime.now(timezone.utc)
    )
    db.add(entry)
    db.flush()

    # 2. Create Journal Lines
    # Debit Expenses
    for line in lines:
        db.add(JournalLine(
            entry_id=entry.id,
            account_id=line.account_id,
            third_party_id=bill.third_party_id,
            project_id=line.project_id,
            fund_id=line.fund_id,
            budget_line_id=line.budget_line_id,
            currency_code=bill.currency_code,
            exchange_rate=bill.exchange_rate,
            foreign_debit=line.foreign_amount,
            base_debit=line.base_amount,
            description=line.description
        ))

    # Credit Supplier (401)
    db.add(JournalLine(
        entry_id=entry.id,
        account_id=third_party.id,  # The supplier's control account
        third_party_id=bill.third_party_id,
        currency_code=bill.currency_code,
        exchange_rate=bill.exchange_rate,
        foreign_credit=net_payable_base / bill.exchange_rate if bill.currency_code != "XAF" else net_payable_base,
        base_credit=net_payable_base,
        description="Net payable to supplier"
    ))

    # Credit Withholding Tax (447) if applicable
    if bill.withholding_tax_base > 0:
        acc_447 = db.query(Account).filter(Account.code.like("447%")).first()
        db.add(JournalLine(
            entry_id=entry.id,
            account_id=acc_447.id,
            currency_code="XAF",
            exchange_rate=Decimal("1.000000"),
            base_credit=bill.withholding_tax_base,
            description="Retenue à la source"
        ))

    bill.status = EntryStatus.POSTED
    bill.journal_entry_id = entry.id
    db.commit()
    db.refresh(bill)
    return bill