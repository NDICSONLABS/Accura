from datetime import date
from decimal import Decimal

from sqlalchemy import String, Date, Enum, ForeignKey, Numeric, Boolean
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import EntryStatus


class SupplierBill(Base, TimestampMixin):
    __tablename__ = "supplier_bills"

    id: Mapped[int] = mapped_column(primary_key=True)
    third_party_id: Mapped[int] = mapped_column(ForeignKey("third_parties.id"))
    bill_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500))

    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), default="XAF")
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1.000000"))

    withholding_tax_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    deductible_vat_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    vat_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))

    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.DRAFT)
    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("accounting_periods.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SupplierBillLine(Base):
    __tablename__ = "supplier_bill_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    bill_id: Mapped[int] = mapped_column(ForeignKey("supplier_bills.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"))
    budget_line_id: Mapped[int | None] = mapped_column(ForeignKey("budget_lines.id"))

    description: Mapped[str | None] = mapped_column(String(255))

    # base_amount is the net (HT) amount in XAF.
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    vat_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    vat_deductible: Mapped[bool] = mapped_column(Boolean, default=False)
    is_vat_capitalized: Mapped[bool] = mapped_column(Boolean, default=False)

    foreign_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))


class TreasurySettlement(Base, TimestampMixin):
    __tablename__ = "treasury_settlements"

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_date: Mapped[date] = mapped_column(Date)
    journal_code: Mapped[str] = mapped_column(String(10))
    reference: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500))

    third_party_id: Mapped[int | None] = mapped_column(ForeignKey("third_parties.id"))
    treasury_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))

    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"), default="XAF")
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6), default=Decimal("1.000000"))

    total_base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    fx_gain_loss_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))

    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.DRAFT)
    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("accounting_periods.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class SettlementAllocation(Base):
    __tablename__ = "settlement_allocations"

    id: Mapped[int] = mapped_column(primary_key=True)
    settlement_id: Mapped[int] = mapped_column(ForeignKey("treasury_settlements.id"))
    bill_id: Mapped[int] = mapped_column(ForeignKey("supplier_bills.id"))

    allocated_foreign_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    allocated_base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    cash_base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))

    # Positive = realized gain (credit 776). Negative = realized loss (debit 676).
    fx_gain_loss_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))