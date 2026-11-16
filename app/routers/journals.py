from datetime import date
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation

from fastapi import APIRouter, Depends, Request, Form, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.enums import FiscalYearStatus, PeriodStatus, EntryStatus
from app.models.master_data import AccountingJournal
from app.models.period import FiscalYear, AccountingPeriod
from app.services.ledger_service import (
    create_and_validate_entry,
    post_journal_entry,
    reverse_journal_entry,
    list_journal_entries,
    get_journal_entry_detail,
    JournalEntryCreateSchema,
    JournalLineSchema,
    JournalListFilters,
)

router = APIRouter(prefix="/accounting/journals", tags=["Journals"])


def _item(values: list[str] | None, index: int) -> str:
    if not values or index >= len(values):
        return ""
    return values[index] or ""


def _optional_int(value: str) -> int | None:
    value = (value or "").strip()
    if not value:
        return None
    try:
        return int(value)
    except ValueError:
        return None


def _base_amount(value: str) -> Decimal:
    value = (value or "").strip()
    if not value:
        return Decimal("0")
    try:
        return Decimal(value).quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return Decimal("0")


# ---------------------------------------------------------------- LIST


@router.get("/", response_class=HTMLResponse)
async def journal_list(
    request: Request,
    fy_id: str | None = None,
    journal_id: str | None = None,
    status: str | None = None,
    search: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    filters = JournalListFilters(
        fiscal_year_id=int(fy_id) if fy_id and fy_id.strip() else None,
        journal_id=int(journal_id) if journal_id and journal_id.strip() else None,
        status=EntryStatus(status) if status and status.strip() else None,
        search=search.strip() if search and search.strip() else None,
        date_from=date.fromisoformat(date_from) if date_from else None,
        date_to=date.fromisoformat(date_to) if date_to else None,
    )

    rows = list_journal_entries(db, filters)

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "accounting/journals/_list_rows.html",
            {"rows": rows},
        )

    return templates.TemplateResponse(
        request,
        "accounting/journals/list.html",
        {
            "title": "Journal des Écritures",
            "rows": rows,
            "filters": filters,
            "fiscal_years": db.query(FiscalYear).all(),
            "journals": db.query(AccountingJournal).all(),
            "statuses": list(EntryStatus),
            "user": user,
        },
    )


# ---------------------------------------------------------------- NEW FORM


@router.get("/new", response_class=HTMLResponse)
async def new_journal_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    journals = db.query(AccountingJournal).order_by(AccountingJournal.code).all()
    fiscal_years = (
        db.query(FiscalYear)
        .filter(FiscalYear.status == FiscalYearStatus.OPEN)
        .order_by(FiscalYear.code)
        .all()
    )

    periods = []
    if fiscal_years:
        periods = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.fiscal_year_id == fiscal_years[0].id,
                AccountingPeriod.status == PeriodStatus.OPEN,
            )
            .order_by(AccountingPeriod.period_number)
            .all()
        )

    return templates.TemplateResponse(
        request,
        "accounting/journals/new.html",
        {
            "title": "Nouvelle Écriture",
            "journals": journals,
            "fiscal_years": fiscal_years,
            "periods": periods,
            "user": user,
        },
    )


@router.get("/periods", response_class=HTMLResponse)
async def period_options(
    request: Request,
    fiscal_year_code: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    periods = []
    fiscal_year = (
        db.query(FiscalYear).filter(FiscalYear.code == fiscal_year_code).first()
    )

    if fiscal_year:
        periods = (
            db.query(AccountingPeriod)
            .filter(
                AccountingPeriod.fiscal_year_id == fiscal_year.id,
                AccountingPeriod.status == PeriodStatus.OPEN,
            )
            .order_by(AccountingPeriod.period_number)
            .all()
        )

    return templates.TemplateResponse(
        request,
        "accounting/journals/_period_options.html",
        {"periods": periods},
    )


# ---------------------------------------------------------------- CREATE


@router.post("/create", response_class=HTMLResponse)
async def create_journal_endpoint(
    request: Request,
    journal_code: str = Form(...),
    fiscal_year_code: str = Form(...),
    period_id: int = Form(...),
    entry_date: str = Form(...),
    description: str = Form(...),
    reference: str | None = Form(default=None),
    account_codes: list[str] = Form(...),
    third_party_ids: list[str] | None = Form(default=None),
    debits: list[str] | None = Form(default=None),
    credits: list[str] | None = Form(default=None),
    line_descriptions: list[str] | None = Form(default=None),
    fund_ids: list[str] | None = Form(default=None),
    project_ids: list[str] | None = Form(default=None),
    budget_line_ids: list[str] | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry_date_value = date.fromisoformat(entry_date)
        lines: list[JournalLineSchema] = []

        for index in range(len(account_codes)):
            account_code = account_codes[index].strip()
            debit = _base_amount(_item(debits, index))
            credit = _base_amount(_item(credits, index))

            if not account_code and debit == Decimal("0") and credit == Decimal("0"):
                continue

            if not account_code:
                raise ValueError("Every non-zero journal line requires an account code.")
            if debit < 0 or credit < 0:
                raise ValueError("Negative amounts are not allowed. Use debit/credit correctly.")
            if debit > 0 and credit > 0:
                raise ValueError("A journal line cannot have both debit and credit.")

            lines.append(
                JournalLineSchema(
                    account_code=account_code,
                    third_party_id=_optional_int(_item(third_party_ids, index)),
                    fund_id=_optional_int(_item(fund_ids, index)),
                    project_id=_optional_int(_item(project_ids, index)),
                    budget_line_id=_optional_int(_item(budget_line_ids, index)),
                    currency_code="XAF",
                    exchange_rate=Decimal("1.000000"),
                    foreign_debit=debit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    foreign_credit=credit.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                    base_debit=debit,
                    base_credit=credit,
                    description=_item(line_descriptions, index).strip() or None,
                )
            )

        if not lines:
            raise ValueError("At least one journal line is required.")

        data = JournalEntryCreateSchema(
            journal_code=journal_code,
            fiscal_year_code=fiscal_year_code,
            period_id=period_id,
            entry_date=entry_date_value,
            reference=reference.strip() if reference and reference.strip() else None,
            description=description,
            lines=lines,
        )

        entry = create_and_validate_entry(db, user.id, data)

        return templates.TemplateResponse(
            request,
            "accounting/journals/_journal_feedback.html",
            {"success": "Journal entry saved as DRAFT.", "entry": entry},
        )

    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "accounting/journals/_journal_feedback.html",
            {"error": str(e)},
            status_code=400,
        )


# ---------------------------------------------------------------- DETAIL


@router.get("/{entry_id}", response_class=HTMLResponse)
async def journal_detail(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    detail = get_journal_entry_detail(db, entry_id)

    if not detail:
        return HTMLResponse(
            f"<h1>404</h1><p>Journal entry {entry_id} not found.</p>",
            status_code=404,
        )

    open_periods = (
        db.query(AccountingPeriod)
        .filter(AccountingPeriod.status == PeriodStatus.OPEN)
        .order_by(AccountingPeriod.start_date)
        .all()
    )

    return templates.TemplateResponse(
        request,
        "accounting/journals/detail.html",
        {
            "title": detail["entry"].voucher_number,
            "open_periods": open_periods,
            "user": user,
            **detail,
        },
    )


# ---------------------------------------------------------------- POST


@router.post("/{entry_id}/post", response_class=HTMLResponse)
async def post_journal_endpoint(
    entry_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        entry = post_journal_entry(db, entry_id, user.id)
        return templates.TemplateResponse(
            request,
            "accounting/journals/_journal_feedback.html",
            {"success": f"Journal entry {entry.voucher_number} has been POSTED.", "entry": entry},
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "accounting/journals/_journal_feedback.html",
            {"error": str(e)},
            status_code=400,
        )


# ---------------------------------------------------------------- REVERSE


@router.post("/{entry_id}/reverse", response_class=HTMLResponse)
async def reverse_journal_endpoint(
    entry_id: int,
    request: Request,
    reversal_date: str = Form(...),
    target_period_id: str | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        reversal = reverse_journal_entry(
            db,
            original_entry_id=entry_id,
            reverser_user_id=user.id,
            reversal_date=date.fromisoformat(reversal_date),
            target_period_id=_optional_int(target_period_id or ""),
        )

        return templates.TemplateResponse(
            request,
            "accounting/journals/_journal_feedback.html",
            {
                "success": f"Reversal posted as {reversal.voucher_number}.",
                "entry": reversal,
            },
        )
    except ValueError as e:
        return templates.TemplateResponse(
            request,
            "accounting/journals/_journal_feedback.html",
            {"error": str(e)},
            status_code=400,
        )