from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.enums import FiscalYearStatus, PeriodStatus
from app.models.master_data import AccountingJournal
from app.models.period import FiscalYear, AccountingPeriod
from app.services.ledger_service import post_journal_entry

router = APIRouter(prefix="/accounting/journals", tags=["Journals"])


@router.get("/new", response_class=HTMLResponse)
async def new_journal_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    journals = db.query(AccountingJournal).all()
    fiscal_years = db.query(FiscalYear).filter(FiscalYear.status == FiscalYearStatus.OPEN).all()

    periods = []
    if fiscal_years:
        periods = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.fiscal_year_id == fiscal_years[0].id,
                AccountingPeriod.status == PeriodStatus.OPEN,
            )
            .all()
        )

    # NOTE: `settings` is auto-injected by the templates wrapper — no need to query it here.
    return templates.TemplateResponse(request, "accounting/journals/new.html", {
        "title": "Nouvelle Écriture",
        "journals": journals,
        "fiscal_years": fiscal_years,
        "periods": periods,
        "user": user,
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
    user: User = Depends(get_current_user),
):
    # MVP stub: in production, parse the nested line items and call create_and_validate_entry.
    return templates.TemplateResponse(request, "accounting/journals/_success_message.html", {
        "message": "Écriture enregistrée en brouillon (DRAFT) avec succès.",
    })


@router.post("/{entry_id}/post", response_class=HTMLResponse)
async def post_journal_endpoint(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry = post_journal_entry(db, entry_id, user.id)
        return templates.TemplateResponse(request, "accounting/journals/_success_message.html", {
            "message": f"Écriture {entry.voucher_number} validée et POSTÉE avec succès.",
        })
    except ValueError as e:
        return templates.TemplateResponse(request, "accounting/journals/_error_message.html", {
            "error": str(e),
        }, status_code=400)