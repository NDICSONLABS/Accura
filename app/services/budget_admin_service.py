from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from pydantic import BaseModel, Field

from app.models.master_data import BudgetLine, Fund, Project
from app.models.account import Account
from app.models.period import FiscalYear
from app.models.ledger import JournalLine, JournalEntry
from app.models.enums import EntryStatus


class BudgetLineSchema(BaseModel):
    account_code: str
    fiscal_year_id: int
    fund_id: int | None = None
    project_id: int | None = None
    approved_amount: Decimal = Field(max_digits=18, decimal_places=0)


def _q0(v: Decimal) -> Decimal:
    return v.quantize(Decimal("1"), rounding=ROUND_HALF_UP)


def get_posted_consumption(db: Session, budget_line_id: int) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(JournalLine.base_debit), 0))
        .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
        .where(
            JournalLine.budget_line_id == budget_line_id,
            JournalEntry.status == EntryStatus.POSTED,
        )
    ).scalar()
    return Decimal(total) if total else Decimal("0")


def list_budget_lines(db: Session, fiscal_year_id: int) -> list[dict]:
    lines = (
        db.query(BudgetLine, Account, Fund, Project)
        .join(Account, BudgetLine.account_id == Account.id)
        .outerjoin(Fund, BudgetLine.fund_id == Fund.id)
        .outerjoin(Project, BudgetLine.project_id == Project.id)
        .filter(BudgetLine.fiscal_year_id == fiscal_year_id)
        .order_by(Account.code)
        .all()
    )

    rows = []
    for line, account, fund, project in lines:
        consumed = get_posted_consumption(db, line.id)
        rows.append({
            "line": line,
            "account": account,
            "fund": fund,
            "project": project,
            "consumed": consumed,
            "remaining": Decimal(line.approved_amount) - consumed,
        })
    return rows


def create_budget_line(db: Session, data: BudgetLineSchema) -> BudgetLine:
    if data.approved_amount < Decimal("0"):
        raise ValueError("Approved budget cannot be negative.")

    account = db.query(Account).filter(Account.code == data.account_code).first()
    if not account or not account.is_postable:
        raise ValueError("Budget account is invalid or not postable.")
    if account.account_class not in (6, 2):
        raise ValueError("Budget lines are allowed only on Class 6 (expense) or Class 2 (asset) accounts.")

    fiscal_year = db.get(FiscalYear, data.fiscal_year_id)
    if not fiscal_year:
        raise ValueError("Fiscal year not found.")

    existing = (
        db.query(BudgetLine)
        .filter(
            BudgetLine.account_id == account.id,
            BudgetLine.fiscal_year_id == data.fiscal_year_id,
            BudgetLine.fund_id == data.fund_id,
            BudgetLine.project_id == data.project_id,
        )
        .first()
    )
    if existing:
        raise ValueError("A budget line already exists for this account / fund / project / year.")

    line = BudgetLine(
        account_id=account.id,
        fiscal_year_id=data.fiscal_year_id,
        fund_id=data.fund_id,
        project_id=data.project_id,
        approved_amount=_q0(data.approved_amount),
    )
    db.add(line)
    db.commit()
    db.refresh(line)
    return line


def update_budget_line(db: Session, budget_line_id: int, approved_amount: Decimal) -> BudgetLine:
    line = db.get(BudgetLine, budget_line_id)
    if not line:
        raise ValueError("Budget line not found.")
    if approved_amount < Decimal("0"):
        raise ValueError("Approved budget cannot be negative.")

    consumed = get_posted_consumption(db, line.id)
    if _q0(approved_amount) < consumed:
        raise ValueError(
            f"Approved budget cannot be reduced below posted consumption. Consumed: {consumed}"
        )

    line.approved_amount = _q0(approved_amount)
    db.commit()
    db.refresh(line)
    return line


def delete_budget_line(db: Session, budget_line_id: int) -> None:
    line = db.get(BudgetLine, budget_line_id)
    if not line:
        raise ValueError("Budget line not found.")

    consumed = get_posted_consumption(db, line.id)
    if consumed > Decimal("0"):
        raise ValueError("Cannot delete a budget line that already has posted consumption.")

    referenced = (
        db.query(JournalLine)
        .filter(JournalLine.budget_line_id == budget_line_id)
        .first()
    )
    if referenced:
        raise ValueError("Cannot delete a budget line referenced by journal entries.")

    db.delete(line)
    db.commit()