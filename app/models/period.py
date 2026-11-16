from sqlalchemy import String, Date, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin
from app.models.enums import FiscalYearStatus, PeriodStatus
from datetime import date

class FiscalYear(Base, TimestampMixin):
    __tablename__ = "fiscal_years"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[FiscalYearStatus] = mapped_column(Enum(FiscalYearStatus), default=FiscalYearStatus.OPEN)

class AccountingPeriod(Base, TimestampMixin):
    __tablename__ = "accounting_periods"

    id: Mapped[int] = mapped_column(primary_key=True)
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("fiscal_years.id"))
    period_number: Mapped[int] = mapped_column()
    start_date: Mapped[date] = mapped_column(Date)
    end_date: Mapped[date] = mapped_column(Date)
    status: Mapped[PeriodStatus] = mapped_column(Enum(PeriodStatus), default=PeriodStatus.OPEN)