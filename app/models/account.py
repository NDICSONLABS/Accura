from sqlalchemy import String, Boolean, Enum, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin
from app.models.enums import NormalBalance

class Account(Base, TimestampMixin):
    __tablename__ = "accounts"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(255))
    account_class: Mapped[int] = mapped_column(Integer)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("accounts.id"))
    normal_balance: Mapped[NormalBalance] = mapped_column(Enum(NormalBalance))
    is_postable: Mapped[bool] = mapped_column(Boolean, default=False)
    requires_third_party: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    default_currency_code: Mapped[str | None] = mapped_column(String(3), ForeignKey("currencies.code"))