from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import String, Date, DateTime, Enum, ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import EntryStatus, FxDirection


class FxRevaluationRun(Base, TimestampMixin):
    __tablename__ = "fx_revaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("fiscal_years.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("accounting_periods.id"))
    as_of_date: Mapped[date] = mapped_column(Date)

    status: Mapped[EntryStatus] = mapped_column(Enum(EntryStatus), default=EntryStatus.DRAFT)
    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    reversal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))

    total_latent_loss_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    total_latent_gain_base: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))

    provision_expense_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    provision_account_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    provision_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class FxRevaluationLine(Base):
    __tablename__ = "fx_revaluation_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("fx_revaluation_runs.id"))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    third_party_id: Mapped[int | None] = mapped_column(ForeignKey("third_parties.id"))
    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"))

    foreign_balance: Mapped[Decimal] = mapped_column(Numeric(18, 2))
    historical_base: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    closing_rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    revalued_base: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    difference_base: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    direction: Mapped[FxDirection] = mapped_column(Enum(FxDirection))


class FiscalYearClose(Base):
    __tablename__ = "fiscal_year_closes"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("fiscal_years.id"), unique=True)
    result_base: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    result_entry_id: Mapped[int] = mapped_column(ForeignKey("journal_entries.id"))
    next_fiscal_year_id: Mapped[int | None] = mapped_column(ForeignKey("fiscal_years.id"))
    carry_forward_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    closed_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    closed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))