from sqlalchemy import Boolean, Enum, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin
from app.models.enums import BudgetEnforcementMode


class OrganizationSetting(Base, TimestampMixin):
    __tablename__ = "organization_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    multi_currency_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    donor_fund_tracking_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    project_cost_center_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    budget_control_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    budget_enforcement_mode: Mapped[BudgetEnforcementMode] = mapped_column(
        Enum(BudgetEnforcementMode), default=BudgetEnforcementMode.NONE
    )
    maker_checker_approval_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    tax_withholding_enabled: Mapped[bool] = mapped_column(Boolean, default=False)

    default_unrestricted_fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"))
    default_project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))