from sqlalchemy.orm import Session
from sqlalchemy import func, select
from decimal import Decimal, ROUND_HALF_UP
from app.models.master_data import BudgetLine, Fund, Project
from app.models.account import Account
from app.models.ledger import JournalLine, JournalEntry
from app.models.accruals import SupplierBillLine, SupplierBill
from app.models.enums import EntryStatus
from app.models.currency import ExchangeRate
from pydantic import BaseModel


class BudgetLineReport(BaseModel):
    budget_line_id: int
    account_code: str
    account_label: str
    approved_budget: Decimal
    committed: Decimal
    actual_posted: Decimal
    remaining: Decimal
    burn_rate: Decimal  # percentage 0-100


def get_budget_vs_actual(
    db: Session,
    fiscal_year_id: int,
    fund_id: int | None = None,
    project_id: int | None = None,
    view_currency: str = "XAF",
    rate_mode: str = "SPOT",
    grant_id: int | None = None,
) -> list[BudgetLineReport]:
    """
    Build the Budget vs. Actual report.
    view_currency is the TARGET currency code (e.g. "XAF", "USD").
    Amounts are converted from the XAF ledger to the target currency when needed.
    rate_mode:
      SPOT           -> latest ExchangeRate for the target currency
      GRANT_WEIGHTED -> tranche weighted-average rate of the selected grant
    """
    # 1. Resolve the conversion rate for grant-currency view

    conversion_rate = Decimal("1")

    if view_currency != "XAF":
        if rate_mode == "GRANT_WEIGHTED" and grant_id:
            from app.services.grant_service import get_grant_weighted_rate
            conversion_rate = get_grant_weighted_rate(db, grant_id)
        else:
            rate_row = (
                db.query(ExchangeRate)
                .filter(ExchangeRate.currency_code == view_currency)
                .order_by(ExchangeRate.effective_date.desc())
                .first()
            )
            if rate_row and rate_row.rate and rate_row.rate > 0:
                conversion_rate = rate_row.rate

    # 2. Load matching budget lines
    budget_query = db.query(BudgetLine).filter(BudgetLine.fiscal_year_id == fiscal_year_id)
    if fund_id:
        budget_query = budget_query.filter(BudgetLine.fund_id == fund_id)
    if project_id:
        budget_query = budget_query.filter(BudgetLine.project_id == project_id)
    budget_lines = budget_query.all()

    reports: list[BudgetLineReport] = []
    for bl in budget_lines:
        account = db.get(Account, bl.account_id)
        approved_xaf = Decimal(bl.approved_amount) if bl.approved_amount else Decimal("0")

        # 3. Actual posted: sum of base_debit for POSTED entries linked to this budget line
        actual_xaf = db.execute(
            select(func.coalesce(func.sum(JournalLine.base_debit), 0))
            .join(JournalEntry, JournalLine.entry_id == JournalEntry.id)
            .where(
                JournalLine.budget_line_id == bl.id,
                JournalEntry.status == EntryStatus.POSTED,
            )
        ).scalar()
        actual_xaf = Decimal(actual_xaf) if actual_xaf else Decimal("0")

        # 4. Committed: sum of UNPOSTED supplier bill lines linked to this budget line
        committed_xaf = db.execute(
            select(func.coalesce(func.sum(SupplierBillLine.base_amount), 0))
            .join(SupplierBill, SupplierBillLine.bill_id == SupplierBill.id)
            .where(
                SupplierBillLine.budget_line_id == bl.id,
                SupplierBill.status != EntryStatus.POSTED,
            )
        ).scalar()
        committed_xaf = Decimal(committed_xaf) if committed_xaf else Decimal("0")

        # 5. Convert to target currency if needed
        approved = approved_xaf
        actual = actual_xaf
        committed = committed_xaf
        if view_currency != "XAF" and conversion_rate > 0:
            approved = (approved_xaf / conversion_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            actual = (actual_xaf / conversion_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            committed = (committed_xaf / conversion_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        remaining = approved - actual - committed
        burn_rate = (actual / approved * Decimal("100")) if approved > 0 else Decimal("0")

        reports.append(BudgetLineReport(
            budget_line_id=bl.id,
            account_code=account.code if account else "",
            account_label=account.label if account else "",
            approved_budget=approved,
            committed=committed,
            actual_posted=actual,
            remaining=remaining,
            burn_rate=burn_rate.quantize(Decimal("0.1"), rounding=ROUND_HALF_UP),
        ))

    return reports