from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import String, Date, DateTime, Enum, ForeignKey, Numeric, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base, TimestampMixin
from app.models.enums import DepreciationMethod, AssetStatus, DepreciationStatus


class FixedAsset(Base, TimestampMixin):
    __tablename__ = "fixed_assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(30), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255))

    acquisition_date: Mapped[date] = mapped_column(Date)
    in_service_date: Mapped[date] = mapped_column(Date)

    acquisition_cost: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    residual_value: Mapped[Decimal] = mapped_column(Numeric(18, 0), default=Decimal("0"))
    useful_life_months: Mapped[int] = mapped_column(Integer)

    method: Mapped[DepreciationMethod] = mapped_column(
        Enum(DepreciationMethod), default=DepreciationMethod.STRAIGHT_LINE
    )
    declining_rate_percent: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))

    status: Mapped[AssetStatus] = mapped_column(Enum(AssetStatus), default=AssetStatus.ACTIVE)

    asset_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    expense_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    accum_account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

    fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))

    created_by_id: Mapped[int] = mapped_column(ForeignKey("users.id"))


class DepreciationScheduleLine(Base, TimestampMixin):
    __tablename__ = "depreciation_schedule_lines"
    __table_args__ = (
        UniqueConstraint("asset_id", "period_id", name="uq_depreciation_asset_period"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("fixed_assets.id"))
    period_id: Mapped[int] = mapped_column(ForeignKey("accounting_periods.id"))

    period_start: Mapped[date] = mapped_column(Date)
    period_end: Mapped[date] = mapped_column(Date)

    proposed_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))

    status: Mapped[DepreciationStatus] = mapped_column(
        Enum(DepreciationStatus), default=DepreciationStatus.SCHEDULED
    )

    journal_entry_id: Mapped[int | None] = mapped_column(ForeignKey("journal_entries.id"))
    posted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))