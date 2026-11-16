from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.period import FiscalYear
from app.models.master_data import Fund, Project
from app.services.budget_service import get_budget_vs_actual

router = APIRouter(prefix="/budget", tags=["Budget"])


@router.get("/report", response_class=HTMLResponse)
async def budget_report(
    request: Request,
    fy_id: int = Query(...),
    fund_id: str | None = None,
    project_id: str | None = None,
    view_currency: str = Query("XAF"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fund_id_int = int(fund_id) if fund_id and fund_id.strip() else None
    project_id_int = int(project_id) if project_id and project_id.strip() else None

    display_currency = "XAF"

    if view_currency == "GRANT" and fund_id_int:
        fund = db.get(Fund, fund_id_int)
        if fund and fund.currency_code:
            display_currency = fund.currency_code

    rows = get_budget_vs_actual(
        db,
        fiscal_year_id=fy_id,
        fund_id=fund_id_int,
        project_id=project_id_int,
        view_currency=display_currency,
    )

    fiscal_years = db.query(FiscalYear).all()
    funds = db.query(Fund).all()
    projects = db.query(Project).all()

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "budget/_budget_table.html",
            {
                "rows": rows,
                "display_currency": display_currency,
            },
        )

    return templates.TemplateResponse(
        request,
        "budget/report.html",
        {
            "title": "Suivi Budgétaire",
            "rows": rows,
            "fiscal_years": fiscal_years,
            "funds": funds,
            "projects": projects,
            "fy_id": fy_id,
            "fund_id": fund_id_int,
            "project_id": project_id_int,
            "view_currency": view_currency,
            "display_currency": display_currency,
            "user": user,
        },
    )