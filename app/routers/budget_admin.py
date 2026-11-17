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
from app.models.period import FiscalYear
from app.models.master_data import Fund, Project
from app.services.budget_admin_service import (
    list_budget_lines, create_budget_line, update_budget_line, delete_budget_line,
    BudgetLineSchema,
)

router = APIRouter(prefix="/budget/admin", tags=["Budget Administration"])


def _dec(value: str | None) -> Decimal:
    try:
        return Decimal((value or "0").strip() or "0")
    except InvalidOperation:
        return Decimal("0")


def _opt_int(value: str | None) -> int | None:
    value = (value or "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None


@router.get("/", response_class=HTMLResponse)
async def budget_admin_page(
    request: Request,
    fy_id: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    fiscal_years = db.query(FiscalYear).order_by(FiscalYear.code).all()
    fy_id_int = _opt_int(fy_id) or (fiscal_years[0].id if fiscal_years else None)
    rows = list_budget_lines(db, fy_id_int) if fy_id_int else []

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "budget/_budget_line_rows.html", {"rows": rows})

    return templates.TemplateResponse(request, "budget/admin.html", {
        "title": "Maintenance Budgétaire",
        "rows": rows,
        "fiscal_years": fiscal_years,
        "fy_id": fy_id_int,
        "accounts": db.query(Account).filter(Account.account_class.in_([6, 2]), Account.is_postable == True).order_by(Account.code).all(),
        "funds": db.query(Fund).order_by(Fund.code).all(),
        "projects": db.query(Project).order_by(Project.code).all(),
        "user": user,
    })


@router.post("/create", response_class=HTMLResponse)
async def create_budget_line_endpoint(
    request: Request,
    account_code: str = Form(...),
    fiscal_year_id: int = Form(...),
    fund_id: str | None = Form(default=None),
    project_id: str | None = Form(default=None),
    approved_amount: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        create_budget_line(db, BudgetLineSchema(
            account_code=account_code,
            fiscal_year_id=fiscal_year_id,
            fund_id=_opt_int(fund_id),
            project_id=_opt_int(project_id),
            approved_amount=_dec(approved_amount),
        ))
        return templates.TemplateResponse(request, "budget/_admin_feedback.html",
            {"success": "Budget line created."})
    except ValueError as e:
        return templates.TemplateResponse(request, "budget/_admin_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/{budget_line_id}/update", response_class=HTMLResponse)
async def update_budget_line_endpoint(
    budget_line_id: int,
    request: Request,
    approved_amount: str = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        update_budget_line(db, budget_line_id, _dec(approved_amount))
        return templates.TemplateResponse(request, "budget/_admin_feedback.html",
            {"success": "Budget line updated."})
    except ValueError as e:
        return templates.TemplateResponse(request, "budget/_admin_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/{budget_line_id}/delete", response_class=HTMLResponse)
async def delete_budget_line_endpoint(
    budget_line_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        delete_budget_line(db, budget_line_id)
        return templates.TemplateResponse(request, "budget/_admin_feedback.html",
            {"success": "Budget line deleted."})
    except ValueError as e:
        return templates.TemplateResponse(request, "budget/_admin_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)