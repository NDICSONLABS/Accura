from datetime import date
from decimal import Decimal, InvalidOperation

from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role
from app.core.templates import templates
from app.core.i18n import translate_message
from app.models.user import User
from app.models.enums import UserRole
from app.models.period import FiscalYear, AccountingPeriod
from app.models.closing import FxRevaluationRun
from app.services.closing_service import (
    soft_lock_period, get_fx_exposures, create_fx_revaluation,
    reverse_fx_revaluation, get_revaluation_detail,
    get_closing_checklist, close_fiscal_year,
    open_next_fiscal_year, carry_forward_result,
    FxRevaluationSchema, FxRateSchema,
)

router = APIRouter(prefix="/closing", tags=["Closing Engine"])

APPROVER = Depends(require_role(UserRole.FINANCE_MANAGER_APPROVER, UserRole.SYSTEM_ADMIN))


def _dec(value: str | None, default: str = "0") -> Decimal:
    try:
        return Decimal((value or default).strip() or default)
    except InvalidOperation:
        return Decimal(default)


@router.get("/", response_class=HTMLResponse)
async def closing_dashboard(
    request: Request,
    fy_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    years = db.query(FiscalYear).order_by(FiscalYear.code).all()
    selected = None
    for year in years:
        if fy_id and str(year.id) == fy_id:
            selected = year
            break
    if selected is None and years:
        selected = years[-1]

    checklist = get_closing_checklist(db, selected.id) if selected else None
    runs = (
        db.query(FxRevaluationRun)
        .filter(FxRevaluationRun.fiscal_year_id == selected.id)
        .order_by(FxRevaluationRun.as_of_date)
        .all()
    ) if selected else []

    return templates.TemplateResponse(request, "closing/dashboard.html", {
        "title": "Clôture", "years": years, "selected": selected,
        "checklist": checklist, "runs": runs, "user": user,
    })


@router.post("/soft-lock", response_class=HTMLResponse)
async def soft_lock_endpoint(
    request: Request,
    period_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    try:
        soft_lock_period(db, period_id, user.id)
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"success": "Period soft-locked."})
    except ValueError as e:
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/fx", response_class=HTMLResponse)
async def fx_wizard(
    request: Request,
    period_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    period = db.get(AccountingPeriod, period_id)
    if not period:
        return HTMLResponse("<h1>404</h1><p>Period not found.</p>", status_code=404)

    exposures = get_fx_exposures(db, period.end_date)
    currencies = sorted({e["currency_code"] for e in exposures})

    return templates.TemplateResponse(request, "closing/fx.html", {
        "title": "Réévaluation FX", "period": period,
        "exposures": exposures, "currencies": currencies, "user": user,
    })


@router.post("/fx/run", response_class=HTMLResponse)
async def fx_run_endpoint(
    request: Request,
    period_id: int = Form(...),
    currency_codes: list[str] = Form(...),
    closing_rates: list[str] = Form(...),
    provision_expense_account_code: str | None = Form(default=None),
    provision_account_code: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    try:
        rates = [
            FxRateSchema(currency_code=code, closing_rate=_dec(closing_rates[i], "0"))
            for i, code in enumerate(currency_codes)
            if _dec(closing_rates[i], "0") > Decimal("0")
        ]
        run = create_fx_revaluation(db, user.id, FxRevaluationSchema(
            period_id=period_id, rates=rates,
            provision_expense_account_code=(provision_expense_account_code or "").strip() or None,
            provision_account_code=(provision_account_code or "").strip() or None,
        ))
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"success": "FX revaluation posted.", "run": run})
    except ValueError as e:
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/fx/{run_id}", response_class=HTMLResponse)
async def fx_detail(
    run_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    detail = get_revaluation_detail(db, run_id)
    if not detail:
        return HTMLResponse("<h1>404</h1><p>Run not found.</p>", status_code=404)
    return templates.TemplateResponse(request, "closing/fx_detail.html",
                                      {"title": "Réévaluation FX", "user": user, **detail})


@router.post("/fx/{run_id}/reverse", response_class=HTMLResponse)
async def fx_reverse_endpoint(
    run_id: int,
    request: Request,
    reversal_date: str = Form(...),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    try:
        run = reverse_fx_revaluation(db, run_id, user.id, date.fromisoformat(reversal_date))
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"success": "FX revaluation reversed.", "run": run})
    except ValueError as e:
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/year/close", response_class=HTMLResponse)
async def year_close_endpoint(
    request: Request,
    fiscal_year_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    try:
        record = close_fiscal_year(db, fiscal_year_id, user.id)
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"success": "Fiscal year closed.", "record": record})
    except ValueError as e:
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/year/open-next", response_class=HTMLResponse)
async def open_next_endpoint(
    request: Request,
    fiscal_year_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    try:
        next_fy = open_next_fiscal_year(db, fiscal_year_id)
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"success": "Next fiscal year opened.", "next_fy": next_fy})
    except ValueError as e:
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/year/carry-forward", response_class=HTMLResponse)
async def carry_forward_endpoint(
    request: Request,
    fiscal_year_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = APPROVER,
):
    try:
        entry = carry_forward_result(db, fiscal_year_id, user.id)
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"success": "Result carried forward.", "entry": entry})
    except ValueError as e:
        return templates.TemplateResponse(request, "closing/_feedback.html",
                                          {"error": translate_message(request, str(e))}, status_code=400)