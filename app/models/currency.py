from sqlalchemy import String, Boolean, Numeric, Date, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin
from decimal import Decimal
from datetime import date

class Currency(Base):
    __tablename__ = "currencies"

    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(50))
    is_functional: Mapped[bool] = mapped_column(Boolean, default=False)

class ExchangeRate(Base, TimestampMixin):
    __tablename__ = "exchange_rates"

    id: Mapped[int] = mapped_column(primary_key=True)
    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"))
    rate: Mapped[Decimal] = mapped_column(Numeric(18, 6))
    effective_date: Mapped[date] = mapped_column(Date)