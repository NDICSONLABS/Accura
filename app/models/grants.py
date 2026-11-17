from datetime import date
from decimal import Decimal

from sqlalchemy import String, Date, Enum, ForeignKey, Numeric, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import EntryStatus, GrantStatus, TrancheStatus


class DonorGrant(Base, TimestampMixin):
    __tablename__ = "donor_grants"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255))

    donor_third_party_id: Mapped[int] = mapped_column(ForeignKey("third_parties.id"))
    fund_id: Mapped[int] = mapped_column(ForeignKey("funds.id"))
    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"))

    total_committed_foreign: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)

    fund_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    receivable_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    status: Mapped[GrantStatus] = mapped_column(Enum(GrantStatus), default=GrantStatus.DRAFT)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class GrantTranche(Base, TimestampMixin):
    __tablename__ = "grant_tranches"
    __table_args__ = (
        UniqueConstraint("grant_id", "tranche_number", name="uq_grant_tranche_number"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("donor_grants.id"))
    tranche_number: Mapped[int] = mapped_column(Integer)
    expected_date: Mapped[date] = mapped_column(Date)
    foreign_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    status: Mapped[TrancheStatus] = mapped_column(Enum(TrancheStatus), default=TrancheStatus.PLANNED)


class FundCall(Base, TimestampMixin):
    __tablename__ = "fund_calls"

    id: Mapped[int] = mapped_column(primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("donor_grants.id"))
    tranche_id: Mapped[int | None] = mapped_column(ForeignKey("grant_tranches.id"))

    call_date: Mapped[date] = mapped_column(Date)
    due_date: Mapped[date] = mapped_column(Date)
    reference: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500))

    foreign_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))

    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.DRAFT)
    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("accounting_periods.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class GrantReceipt(Base, TimestampMixin):
    __tablename__ = "grant_receipts"

    id: Mapped[int] = mapped_column(primary_key=True)
    fund_call_id: Mapped[int] = mapped_column(ForeignKey("fund_calls.id"))

    receipt_date: Mapped[date] = mapped_column(Date)
    journal_code: Mapped[str] = mapped_column(String(10))
    treasury_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    reference: Mapped[str] = mapped_column(String(50))
    description: Mapped[str] = mapped_column(String(500))

    foreign_amount: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    base_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    receivable_cleared_base: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    fx_gain_loss_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))

    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.DRAFT)
    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    period_id: Mapped[int | None] = mapped_column(ForeignKey("accounting_periods.id"))
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))