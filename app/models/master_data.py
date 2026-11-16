import sqlalchemy as sa
from sqlalchemy import String, Boolean, ForeignKey, Numeric, Integer
from sqlalchemy.orm import Mapped, mapped_column
from app.core.database import Base, TimestampMixin
from decimal import Decimal

class AccountingJournal(Base, TimestampMixin):
    __tablename__ = "accounting_journals"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(10), unique=True)
    label: Mapped[str] = mapped_column(String(100))
    journal_type: Mapped[str] = mapped_column(String(50))

class ThirdParty(Base, TimestampMixin):
    __tablename__ = "third_parties"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    tax_id: Mapped[str | None] = mapped_column(String(50))
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))

class Fund(Base, TimestampMixin):
    __tablename__ = "funds"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    label: Mapped[str] = mapped_column(String(255))
    donor_name: Mapped[str | None] = mapped_column(String(255))
    currency_code: Mapped[str] = mapped_column(String(3), ForeignKey("currencies.code"))
    is_restricted: Mapped[bool] = mapped_column(Boolean, default=False)

class Project(Base, TimestampMixin):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(20), unique=True)
    label: Mapped[str] = mapped_column(String(255))
    fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"))

class BudgetLine(Base, TimestampMixin):
    __tablename__ = "budget_lines"

    id: Mapped[int] = mapped_column(primary_key=True)
    account_id: Mapped[int] = mapped_column(ForeignKey("accounts.id"))
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"))
    fund_id: Mapped[int | None] = mapped_column(ForeignKey("funds.id"))
    fiscal_year_id: Mapped[int] = mapped_column(ForeignKey("fiscal_years.id"))
    approved_amount: Mapped[Decimal] = mapped_column(Numeric(18, 0))

class JournalSequence(Base, TimestampMixin):
    __tablename__ = "journal_sequences"

    id: Mapped[int] = mapped_column(primary_key=True)
    journal_code: Mapped[str] = mapped_column(String(10))
    fiscal_year_code: Mapped[str] = mapped_column(String(10))
    current_sequence: Mapped[int] = mapped_column(Integer, default=0)

    # Unique constraint to prevent duplicate sequences for same journal/year
    __table_args__ = (
        sa.UniqueConstraint('journal_code', 'fiscal_year_code', name='uq_journal_fiscal_year'),
    )