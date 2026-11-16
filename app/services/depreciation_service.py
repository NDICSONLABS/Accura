from datetime import date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from sqlalchemy.orm import Session
from sqlalchemy import func, select
from pydantic import BaseModel, Field

from app.models.fixed_asset import FixedAsset, DepreciationScheduleLine
from app.models.account import Account
from app.models.period import AccountingPeriod, FiscalYear
from app.models.master_data import AccountingJournal
from app.models.enums import (
    DepreciationMethod,
    AssetStatus,
    DepreciationStatus,
    PeriodStatus,
    FiscalYearStatus,
)
from app.models.settings import OrganizationSetting
from app.services.ledger_service import (
    create_and_validate_entry,
    post_journal_entry,
    JournalEntryCreateSchema,
    JournalLineSchema,
)

XAF_ZERO = Decimal("1")


class FixedAssetCreateSchema(BaseModel):
    code: str
    label: str
    acquisition_date: date
    in_service_date: date
    acquisition_cost: Decimal = Field(max_digits=18, decimal_places=0)
    residual_value: Decimal = Field(default=Decimal("0"), max_digits=18, decimal_places=0)
    useful_life_months: int
    method: DepreciationMethod = DepreciationMethod.STRAIGHT_LINE
    declining_rate_percent: Decimal | None = Field(default=None, max_digits=5, decimal_places=2)
    asset_account_code: str
    expense_account_code: str
    accum_account_code: str
    fund_id: int | None = None
    project_id: int | None = None


def _q(amount: Decimal) -> Decimal:
    return amount.quantize(XAF_ZERO, rounding=ROUND_HALF_UP)


def _posted_accumulated(db: Session, asset_id: int) -> Decimal:
    total = db.execute(
        select(func.coalesce(func.sum(DepreciationScheduleLine.amount), 0))
        .where(
            DepreciationScheduleLine.asset_id == asset_id,
            DepreciationScheduleLine.status == DepreciationStatus.POSTED,
        )
    ).scalar()
    return Decimal(total) if total else Decimal("0")


def create_fixed_asset(db: Session, user_id: int, data: FixedAssetCreateSchema) -> FixedAsset:
    if data.acquisition_cost <= 0:
        raise ValueError("Acquisition cost must be greater than zero.")
    if data.residual_value < 0:
        raise ValueError("Residual value cannot be negative.")
    if data.residual_value >= data.acquisition_cost:
        raise ValueError("Residual value must be less than acquisition cost.")
    if data.useful_life_months <= 0:
        raise ValueError("Useful life must be at least one month.")
    if data.in_service_date < data.acquisition_date:
        raise ValueError("In-service date cannot precede acquisition date.")
    if data.method == DepreciationMethod.DECLINING_BALANCE:
        if not data.declining_rate_percent or data.declining_rate_percent <= 0:
            raise ValueError("Declining balance method requires a positive annual rate.")

    asset_acc = db.query(Account).filter(Account.code == data.asset_account_code).first()
    expense_acc = db.query(Account).filter(Account.code == data.expense_account_code).first()
    accum_acc = db.query(Account).filter(Account.code == data.accum_account_code).first()

    if not asset_acc or asset_acc.account_class != 2:
        raise ValueError("Asset account must be a Class 2 account.")
    if not expense_acc or expense_acc.account_class != 6 or not expense_acc.is_postable:
        raise ValueError("Depreciation expense account must be a postable Class 6 account.")
    if not accum_acc or accum_acc.account_class != 2 or not accum_acc.is_postable:
        raise ValueError("Accumulated depreciation account must be a postable Class 2 account.")

    asset = FixedAsset(
        code=data.code.strip(),
        label=data.label.strip(),
        acquisition_date=data.acquisition_date,
        in_service_date=data.in_service_date,
        acquisition_cost=_q(data.acquisition_cost),
        residual_value=_q(data.residual_value),
        useful_life_months=data.useful_life_months,
        method=data.method,
        declining_rate_percent=data.declining_rate_percent,
        status=AssetStatus.ACTIVE,
        asset_account_id=asset_acc.id,
        expense_account_id=expense_acc.id,
        accum_account_id=accum_acc.id,
        fund_id=data.fund_id,
        project_id=data.project_id,
        created_by_id=user_id,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


def compute_monthly_depreciation(db: Session, asset: FixedAsset) -> Decimal:
    accumulated = _posted_accumulated(db, asset.id)
    net_book_value = Decimal(asset.acquisition_cost) - accumulated
    remaining = net_book_value - Decimal(asset.residual_value)

    if remaining <= 0:
        return Decimal("0")

    if asset.method == DepreciationMethod.STRAIGHT_LINE:
        depreciable = Decimal(asset.acquisition_cost) - Decimal(asset.residual_value)
        monthly = depreciable / Decimal(asset.useful_life_months)
    else:
        rate = Decimal(asset.declining_rate_percent or "0")
        monthly = net_book_value * rate / Decimal("100") / Decimal("12")

    return _q(min(monthly, remaining))


def generate_period_depreciation(db: Session, period_id: int) -> list[DepreciationScheduleLine]:
    period = db.get(AccountingPeriod, period_id)
    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("Cannot generate depreciation: accounting period is not OPEN.")

    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)
    if not fiscal_year or fiscal_year.status != FiscalYearStatus.OPEN:
        raise ValueError("Cannot generate depreciation: fiscal year is not OPEN.")

    assets = (
        db.query(FixedAsset)
        .filter(
            FixedAsset.status == AssetStatus.ACTIVE,
            FixedAsset.in_service_date <= period.end_date,
        )
        .order_by(FixedAsset.code)
        .all()
    )

    lines: list[DepreciationScheduleLine] = []

    for asset in assets:
        existing = (
            db.query(DepreciationScheduleLine)
            .filter(
                DepreciationScheduleLine.asset_id == asset.id,
                DepreciationScheduleLine.period_id == period.id,
            )
            .first()
        )

        if existing and existing.status == DepreciationStatus.POSTED:
            lines.append(existing)
            continue

        amount = compute_monthly_depreciation(db, asset)
        if amount <= 0:
            asset.status = AssetStatus.FULLY_DEPRECIATED
            continue

        if existing:
            existing.proposed_amount = amount
            existing.amount = amount
            existing.period_start = period.start_date
            existing.period_end = period.end_date
            line = existing
        else:
            line = DepreciationScheduleLine(
                asset_id=asset.id,
                period_id=period.id,
                period_start=period.start_date,
                period_end=period.end_date,
                proposed_amount=amount,
                amount=amount,
                status=DepreciationStatus.SCHEDULED,
            )
            db.add(line)

        lines.append(line)

    db.commit()
    for line in lines:
        db.refresh(line)
    return lines


def post_period_depreciation(db: Session, period_id: int, user_id: int):
    period = db.get(AccountingPeriod, period_id)
    if not period or period.status != PeriodStatus.OPEN:
        raise ValueError("Cannot post depreciation: accounting period is not OPEN.")

    fiscal_year = db.get(FiscalYear, period.fiscal_year_id)
    if not fiscal_year or fiscal_year.status != FiscalYearStatus.OPEN:
        raise ValueError("Cannot post depreciation: fiscal year is not OPEN.")

    journal = db.query(AccountingJournal).filter(AccountingJournal.code == "AMOR").first()
    if not journal:
        raise ValueError("Depreciation journal 'AMOR' is missing. Run migrations.")

    scheduled = (
        db.query(DepreciationScheduleLine)
        .filter(
            DepreciationScheduleLine.period_id == period.id,
            DepreciationScheduleLine.status == DepreciationStatus.SCHEDULED,
        )
        .all()
    )

    if not scheduled:
        raise ValueError("No scheduled depreciation lines to post for this period.")

    settings = db.query(OrganizationSetting).first()
    journal_lines: list[JournalLineSchema] = []
    total = Decimal("0")

    for line in scheduled:
        asset = db.get(FixedAsset, line.asset_id)
        expense_acc = db.get(Account, asset.expense_account_id)
        accum_acc = db.get(Account, asset.accum_account_id)
        amount = _q(Decimal(line.amount))

        if amount <= 0:
            continue

        fund_id = asset.fund_id if settings and settings.donor_fund_tracking_enabled else None
        project_id = asset.project_id if settings and settings.project_cost_center_enabled else None

        journal_lines.append(
            JournalLineSchema(
                account_code=expense_acc.code,
                base_debit=amount,
                foreign_debit=amount.quantize(Decimal("0.01")),
                fund_id=fund_id,
                project_id=project_id,
                description=f"Amortissement {asset.code}",
            )
        )
        journal_lines.append(
            JournalLineSchema(
                account_code=accum_acc.code,
                base_credit=amount,
                foreign_credit=amount.quantize(Decimal("0.01")),
                fund_id=fund_id,
                project_id=project_id,
                description=f"Amortissement {asset.code}",
            )
        )
        total += amount

    if total <= 0:
        raise ValueError("Depreciation total is zero; nothing to post.")

    entry_data = JournalEntryCreateSchema(
        journal_code=journal.code,
        fiscal_year_code=fiscal_year.code,
        period_id=period.id,
        entry_date=period.end_date,
        reference=f"DEPR-{fiscal_year.code}-{period.period_number:02d}",
        description=f"Dotation aux amortissements {fiscal_year.code}-{period.period_number:02d}",
        lines=journal_lines,
    )

    entry = create_and_validate_entry(db, user_id, entry_data)
    posted_entry = post_journal_entry(db, entry.id, user_id)

    now = datetime.now(timezone.utc)
    for line in scheduled:
        line.status = DepreciationStatus.POSTED
        line.journal_entry_id = posted_entry.id
        line.posted_at = now

        asset = db.get(FixedAsset, line.asset_id)
        accumulated = _posted_accumulated(db, asset.id) + Decimal(line.amount)
        if accumulated >= Decimal(asset.acquisition_cost) - Decimal(asset.residual_value):
            asset.status = AssetStatus.FULLY_DEPRECIATED

    db.commit()
    db.refresh(posted_entry)
    return posted_entry


def list_assets(db: Session, search: str | None = None) -> list[FixedAsset]:
    query = db.query(FixedAsset)
    if search:
        pattern = f"%{search}%"
        query = query.filter(
            (FixedAsset.code.ilike(pattern)) | (FixedAsset.label.ilike(pattern))
        )
    return query.order_by(FixedAsset.code).all()


def get_asset_detail(db: Session, asset_id: int) -> dict | None:
    asset = db.get(FixedAsset, asset_id)
    if not asset:
        return None

    schedule = (
        db.query(DepreciationScheduleLine, AccountingPeriod)
        .join(AccountingPeriod, DepreciationScheduleLine.period_id == AccountingPeriod.id)
        .filter(DepreciationScheduleLine.asset_id == asset_id)
        .order_by(DepreciationScheduleLine.period_start)
        .all()
    )

    accumulated = _posted_accumulated(db, asset_id)
    nbv = Decimal(asset.acquisition_cost) - accumulated

    return {
        "asset": asset,
        "schedule": schedule,
        "accumulated": accumulated,
        "net_book_value": nbv,
        "asset_account": db.get(Account, asset.asset_account_id),
        "expense_account": db.get(Account, asset.expense_account_id),
        "accum_account": db.get(Account, asset.accum_account_id),
    }