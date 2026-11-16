from sqlalchemy import String, Date, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin
from app.models.enums import EntryStatus
from datetime import date, datetime
from decimal import Decimal


class JournalEntry(Base, TimestampMixin):
    __tablename__ = "journal_entries"

    id: Mapped[int] = mapped_column(primary_key=True)
    journal_id: Mapped[int] = mapped_column(ForeignKey("accounting_journals.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("accounting_periods.id"))
    entry_date: Mapped[date] = mapped_column(Date)
    voucher_number: Mapped[str] = mapped_column(String(50), unique=True)
    reference: Mapped[str | None] = mapped_column(String(100))
    description: Mapped[str] = mapped_column(String(500))
    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.DRAFT)
    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    approved_by_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    posted_at: Mapped[datetime | None] = mapped_column()


class JournalLine(Base):
    __tablename__ = "journal_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    third_party_id: Mapped[int | None] = mapped_column(ForeignKey("third_parties.id"))
    fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    budget_line_id: Mapped[int | None] = mapped_column(ForeignKey("budget_lines.id"))

    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"))
    exchange_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))

    foreign_debit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))
    foreign_credit: Mapped[Decimal] = mapped_column(Numeric(18, 2), default=Decimal("0.00"))

    base_debit: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    base_credit: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))

    description: Mapped[str | None] = mapped_column(String(255))