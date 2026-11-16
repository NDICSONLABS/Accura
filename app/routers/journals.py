from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.enums import UserRole, EntryStatus
from app.services.ledger_service import (
    create_and_validate_entry, post_journal_entry, reverse_journal_entry,
    JournalEntryCreateSchema, JournalLineSchema
)
from app.models.master_data import AccountingJournal
from app.models.period import FiscalYear, AccountingPeriod
from app.models.settings import OrganizationSetting
from datetime import date

router = APIRouter(prefix="/accounting/journals", tags=["Journals"])


@router.get("/new", response_class=HTMLResponse)
async def new_journal_page(
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
) -> HTMLResponse:
    settings = db.query(OrganizationSetting).first()
    journals = db.query(AccountingJournal).all()
    fiscal_years = db.query(FiscalYear).filter(FiscalYear.status == "OPEN").all()

    periods = []
    if fiscal_years:
        periods = db.query(AccountingPeriod).filter(
            AccountingPeriod.fiscal_year_id == fiscal_years[0].id,
            AccountingPeriod.status == "OPEN"
        ).all()

    return templates.TemplateResponse("accounting/journals/new.html", {
        "request": request,
        "journals": journals,
        "fiscal_years": fiscal_years,
        "periods": periods,
        "settings": settings,
        "user": user
    })


@router.post("/create", response_class=HTMLResponse)
async def create_journal_endpoint(
        request: Request,
        journal_code: str = Form(...),
        fiscal_year_code: str = Form(...),
        period_id: int = Form(...),
        entry_date: str = Form(...),
        description: str = Form(...),
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
) -> HTMLResponse:
    try:
        return templates.TemplateResponse("accounting/journals/_success_message.html", {
            "request": request,
            "message": "Écriture enregistrée en brouillon (DRAFT) avec succès."
        })
    except ValueError as e:
        return templates.TemplateResponse("accounting/journals/_error_message.html", {
            "request": request,
            "error": str(e)
        }, status_code=400)


@router.post("/{entry_id}/post", response_class=HTMLResponse)
async def post_journal_endpoint(
        entry_id: int,
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
) -> HTMLResponse:
    try:
        entry = post_journal_entry(db, entry_id, user.id)
        return templates.TemplateResponse("accounting/journals/_success_message.html", {
            "request": request,
            "message": f"Écriture {entry.voucher_number} validée et POSTÉE avec succès."
        })
    except ValueError as e:
        return templates.TemplateResponse("accounting/journals/_error_message.html", {
            "request": request,
            "error": str(e)
        }, status_code=400)