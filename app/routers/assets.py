from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.core.i18n import translate_message
from app.models.user import User
from app.models.account import Account
from app.models.period import AccountingPeriod, FiscalYear
from app.models.enums import PeriodStatus, FiscalYearStatus, DepreciationMethod
from app.services.depreciation_service import (
    create_fixed_asset,
    generate_period_depreciation,
    post_period_depreciation,
    list_assets,
    get_asset_detail,
    FixedAssetCreateSchema,
)

router = APIRouter(prefix="/assets", tags=["Fixed Assets"])


def _decimal(value: str) -> Decimal:
    try:
        return Decimal((value or "0").strip())
    except InvalidOperation:
        return Decimal("0")


@router.get("/", response_class=HTMLResponse)
async def asset_list(
    request: Request,
    search: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    assets = list_assets(db, search)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "assets/_asset_rows.html", {"assets": assets})

    periods = (
        db.query(AccountingPeriod)
        .join(FiscalYear, AccountingPeriod.fiscal_year_id == FiscalYear.id)
        .filter(
            AccountingPeriod.status == PeriodStatus.OPEN,
            FiscalYear.status == FiscalYearStatus.OPEN,
        )
        .order_by(AccountingPeriod.start_date)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "assets/list.html",
        {
            "title": "Immobilisations",
            "assets": assets,
            "search": search or "",
            "periods": periods,
            "user": user,
        },
    )


@router.get("/new", response_class=HTMLResponse)
async def new_asset_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(
        request,
        "assets/new.html",
        {
            "title": "Nouvelle Immobilisation",
            "asset_accounts": db.query(Account).filter(Account.account_class == 2).all(),
            "expense_accounts": db.query(Account).filter(Account.account_class == 6, Account.is_postable == True).all(),
            "accum_accounts": db.query(Account).filter(Account.account_class == 2, Account.is_postable == True).all(),
            "methods": list(DepreciationMethod),
            "user": user,
        },
    )


@router.post("/create", response_class=HTMLResponse)
async def create_asset_endpoint(
    request: Request,
    code: str = Form(...),
    label: str = Form(...),
    acquisition_date: str = Form(...),
    in_service_date: str = Form(...),
    acquisition_cost: str = Form(...),
    residual_value: str = Form("0"),
    useful_life_months: int = Form(...),
    method: str = Form(...),
    declining_rate_percent: str | None = Form(default=None),
    asset_account_code: str = Form(...),
    expense_account_code: str = Form(...),
    accum_account_code: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        asset = create_fixed_asset(
            db,
            user.id,
            FixedAssetCreateSchema(
                code=code,
                label=label,
                acquisition_date=date.fromisoformat(acquisition_date),
                in_service_date=date.fromisoformat(in_service_date),
                acquisition_cost=_decimal(acquisition_cost),
                residual_value=_decimal(residual_value),
                useful_life_months=useful_life_months,
                method=DepreciationMethod(method),
                declining_rate_percent=_decimal(declining_rate_percent) if declining_rate_percent else None,
                asset_account_code=asset_account_code,
                expense_account_code=expense_account_code,
                accum_account_code=accum_account_code,
            ),
        )
        return templates.TemplateResponse(
            request,
            "assets/_feedback.html",
            {"success": "Fixed asset created.", "asset": asset},
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "assets/_feedback.html",
            {"error": translate_message(request, str(e))},
            status_code=400,
        )


@router.get("/depreciation/period", response_class=HTMLResponse)
async def depreciation_period(
    request: Request,
    period_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.models.fixed_asset import DepreciationScheduleLine
    from app.models.fixed_asset import FixedAsset

    lines = (
        db.query(DepreciationScheduleLine, FixedAsset)
        .join(FixedAsset, DepreciationScheduleLine.asset_id == FixedAsset.id)
        .filter(DepreciationScheduleLine.period_id == period_id)
        .order_by(FixedAsset.code)
        .all()
    )
    period = db.get(AccountingPeriod, period_id)

    return templates.TemplateResponse(
        request,
        "assets/depreciation_period.html",
        {
            "title": "Amortissements",
            "lines": lines,
            "period": period,
            "user": user,
        },
    )


@router.post("/depreciation/generate", response_class=HTMLResponse)
async def generate_depreciation(
    request: Request,
    period_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        generate_period_depreciation(db, period_id)
        return templates.TemplateResponse(
            request,
            "assets/_feedback.html",
            {"success": "Depreciation schedule generated."},
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "assets/_feedback.html",
            {"error": translate_message(request, str(e))},
            status_code=400,
        )


@router.post("/depreciation/post", response_class=HTMLResponse)
async def post_depreciation(
    request: Request,
    period_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry = post_period_depreciation(db, period_id, user.id)
        return templates.TemplateResponse(
            request,
            "assets/_feedback.html",
            {"success": f"Depreciation posted as {entry.voucher_number}.", "entry": entry},
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "assets/_feedback.html",
            {"error": translate_message(request, str(e))},
            status_code=400,
        )


@router.get("/{asset_id}", response_class=HTMLResponse)
async def asset_detail(
    asset_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    detail = get_asset_detail(db, asset_id)
    if not detail:
        return HTMLResponse("<h1>404</h1><p>Asset not found.</p>", status_code=404)

    return templates.TemplateResponse(
        request,
        "assets/detail.html",
        {"title": detail["asset"].code, "user": user, **detail},
    )