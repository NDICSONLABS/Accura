from fastapi import APIRouter, Depends, Request, Query, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user, require_role
from app.core.templates import templates
from app.models.user import User
from app.models.enums import UserRole
from app.models.period import FiscalYear, AccountingPeriod
from app.models.settings import OrganizationSetting
from app.services.reporting_service import get_general_ledger, GLFilters, get_trial_balance, close_period
from datetime import date

router = APIRouter(prefix="/reporting", tags=["Reporting"])


@router.get("/gl", response_class=HTMLResponse)
async def general_ledger(
        request: Request,
        fy_id: str | None = None,
        acc_id: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
):
    # Safely parse empty strings to None
    fy_id_int = int(fy_id) if fy_id and fy_id.strip() else None
    acc_id_int = int(acc_id) if acc_id and acc_id.strip() else None
    from_date = date.fromisoformat(date_from) if date_from else None
    to_date = date.fromisoformat(date_to) if date_to else None

    filters = GLFilters(
        fiscal_year_id=fy_id_int,
        account_id=acc_id_int,
        date_from=from_date,
        date_to=to_date
    )
    rows = get_general_ledger(db, filters)
    fiscal_years = db.query(FiscalYear).all()
    return templates.TemplateResponse(request, "reporting/gl.html", {
        "rows": rows, "fiscal_years": fiscal_years, "filters": filters
    })


@router.get("/trial-balance", response_class=HTMLResponse)
async def trial_balance(
        request: Request,
        fy_id: int = Query(...),
        as_of: str = Query(...),
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
):
    as_of_date = date.fromisoformat(as_of)
    rows = get_trial_balance(db, fy_id, as_of_date)
    return templates.TemplateResponse(request, "reporting/trial_balance.html", {"rows": rows})


@router.get("/closing", response_class=HTMLResponse)
async def closing_wizard(
        request: Request,
        fy_id: str | None = None,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
):
    settings = db.query(OrganizationSetting).first()
    query = db.query(AccountingPeriod)

    fy_id_int = int(fy_id) if fy_id and fy_id.strip() else None
    if fy_id_int:
        query = query.filter(AccountingPeriod.fiscal_year_id == fy_id_int)

    periods = query.order_by(AccountingPeriod.start_date).all()

    return templates.TemplateResponse(request, "reporting/closing.html", {
        "periods": periods, "settings": settings
    })


@router.post("/close-period/{period_id}", response_class=HTMLResponse)
async def close_period_endpoint(
        period_id: int,
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(require_role(UserRole.FINANCE_MANAGER_APPROVER))
):
    try:
        period = close_period(db, period_id, user.id)
        return templates.TemplateResponse(request, "reporting/_period_row.html", {"period": period})
    except ValueError as e:
        return HTMLResponse(f"<div class='text-red-600 p-2 font-medium'>Erreur: {e}</div>", status_code=400)