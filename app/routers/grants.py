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
from app.models.master_data import ThirdParty, Fund, AccountingJournal
from app.models.grants import DonorGrant, FundCall, GrantReceipt, GrantTranche
from app.models.currency import Currency
from app.models.enums import TrancheStatus
from app.services.grant_service import (
    create_grant, add_tranche, activate_grant, get_grant_detail,
    create_fund_call, post_fund_call, get_call_outstanding,
    create_grant_receipt, post_grant_receipt,
    GrantCreateSchema, TrancheCreateSchema,
    FundCallCreateSchema, GrantReceiptCreateSchema,
)

router = APIRouter(prefix="/grants", tags=["Donor Grants"])


def _dec(value: str | None, default: str = "0") -> Decimal:
    try:
        return Decimal((value or default).strip() or default)
    except InvalidOperation:
        return Decimal(default)


def _opt_int(value: str | None) -> int | None:
    value = (value or "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None


@router.get("/", response_class=HTMLResponse)
async def grant_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    grants = db.query(DonorGrant).order_by(DonorGrant.code).all()
    rows = [{"grant": g, "donor": db.get(ThirdParty, g.donor_third_party_id)} for g in grants]

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "grants/_grant_rows.html", {"rows": rows})

    return templates.TemplateResponse(request, "grants/list.html", {
        "title": "Conventions de Financement", "rows": rows, "user": user,
    })


@router.get("/new", response_class=HTMLResponse)
async def new_grant_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "grants/new.html", {
        "title": "Nouvelle Convention",
        "donors": db.query(ThirdParty).order_by(ThirdParty.name).all(),
        "funds": db.query(Fund).filter(Fund.is_restricted == True).order_by(Fund.code).all(),
        "currencies": db.query(Currency).order_by(Currency.code).all(),
        "fund_accounts": db.query(Account).filter(Account.account_class == 1, Account.is_postable == True).order_by(Account.code).all(),
        "user": user,
    })


@router.post("/create", response_class=HTMLResponse)
async def create_grant_endpoint(
    request: Request,
    code: str = Form(...),
    label: str = Form(...),
    donor_third_party_id: int = Form(...),
    fund_id: int = Form(...),
    currency_code: str = Form("XAF"),
    total_committed_foreign: str = Form("0.00"),
    start_date: str = Form(...),
    end_date: str = Form(...),
    fund_account_code: str = Form("1611"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        grant = create_grant(db, user.id, GrantCreateSchema(
            code=code, label=label,
            donor_third_party_id=donor_third_party_id,
            fund_id=fund_id,
            currency_code=currency_code,
            total_committed_foreign=_dec(total_committed_foreign, "0.00"),
            start_date=date.fromisoformat(start_date),
            end_date=date.fromisoformat(end_date),
            fund_account_code=fund_account_code,
        ))
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Grant agreement created.", "grant": grant})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/tranches/create", response_class=HTMLResponse)
async def create_tranche_endpoint(
    request: Request,
    grant_id: int = Form(...),
    tranche_number: int = Form(...),
    expected_date: str = Form(...),
    foreign_amount: str = Form(...),
    exchange_rate: str = Form("1.000000"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        add_tranche(db, grant_id, TrancheCreateSchema(
            tranche_number=tranche_number,
            expected_date=date.fromisoformat(expected_date),
            foreign_amount=_dec(foreign_amount, "0.00"),
            exchange_rate=_dec(exchange_rate, "1.000000"),
        ))
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Tranche added.", "grant_id": grant_id})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/activate", response_class=HTMLResponse)
async def activate_grant_endpoint(
    request: Request,
    grant_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        grant = activate_grant(db, grant_id)
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Grant activated.", "grant": grant})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/fund-calls/new", response_class=HTMLResponse)
async def new_fund_call_page(
    request: Request,
    grant_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    detail = get_grant_detail(db, grant_id)
    if not detail:
        return HTMLResponse("<h1>404</h1><p>Grant not found.</p>", status_code=404)

    planned = [t for t in detail["tranches"] if t.status == TrancheStatus.PLANNED]

    return templates.TemplateResponse(request, "grants/fund_call_new.html", {
        "title": "Appel de Fonds", "planned_tranches": planned, "user": user, **detail,
    })


@router.post("/fund-calls/create", response_class=HTMLResponse)
async def create_fund_call_endpoint(
    request: Request,
    grant_id: int = Form(...),
    tranche_id: str | None = Form(default=None),
    call_date: str = Form(...),
    due_date: str = Form(...),
    reference: str = Form(...),
    description: str = Form(...),
    foreign_amount: str = Form(...),
    exchange_rate: str = Form("1.000000"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        call = create_fund_call(db, user.id, FundCallCreateSchema(
            grant_id=grant_id,
            tranche_id=_opt_int(tranche_id),
            call_date=date.fromisoformat(call_date),
            due_date=date.fromisoformat(due_date),
            reference=reference, description=description,
            foreign_amount=_dec(foreign_amount, "0.00"),
            exchange_rate=_dec(exchange_rate, "1.000000"),
        ))
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Fund call saved as DRAFT.", "call": call, "grant_id": grant_id})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/fund-calls/post", response_class=HTMLResponse)
async def post_fund_call_endpoint(
    request: Request,
    call_id: int = Form(...),
    grant_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        call = post_fund_call(db, call_id, user.id)
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Fund call has been POSTED.", "call": call, "grant_id": grant_id})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/receipts/new", response_class=HTMLResponse)
async def new_receipt_page(
    request: Request,
    call_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    call = db.get(FundCall, call_id)
    if not call:
        return HTMLResponse("<h1>404</h1><p>Fund call not found.</p>", status_code=404)

    grant = db.get(DonorGrant, call.grant_id)

    return templates.TemplateResponse(request, "grants/receipt_new.html", {
        "title": "Encaissement Subvention",
        "call": call, "grant": grant,
        "outstanding": get_call_outstanding(db, call),
        "treasury_accounts": db.query(Account).filter(Account.account_class == 5, Account.is_postable == True).order_by(Account.code).all(),
        "journals": db.query(AccountingJournal).filter(AccountingJournal.journal_type.in_(["BANK", "CASH"])).all(),
        "user": user,
    })


@router.post("/receipts/create", response_class=HTMLResponse)
async def create_receipt_endpoint(
    request: Request,
    fund_call_id: int = Form(...),
    receipt_date: str = Form(...),
    journal_code: str = Form(...),
    treasury_account_code: str = Form(...),
    reference: str = Form(...),
    description: str = Form(...),
    foreign_amount: str = Form(...),
    exchange_rate: str = Form("1.000000"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        receipt = create_grant_receipt(db, user.id, GrantReceiptCreateSchema(
            fund_call_id=fund_call_id,
            receipt_date=date.fromisoformat(receipt_date),
            journal_code=journal_code,
            treasury_account_code=treasury_account_code,
            reference=reference, description=description,
            foreign_amount=_dec(foreign_amount, "0.00"),
            exchange_rate=_dec(exchange_rate, "1.000000"),
        ))
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Receipt saved as DRAFT.", "receipt": receipt})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.post("/receipts/post", response_class=HTMLResponse)
async def post_receipt_endpoint(
    request: Request,
    receipt_id: int = Form(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        receipt = post_grant_receipt(db, receipt_id, user.id)
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"success": "Receipt has been POSTED.", "receipt": receipt})
    except ValueError as e:
        return templates.TemplateResponse(request, "grants/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/{grant_id}", response_class=HTMLResponse)
async def grant_detail(
    grant_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    detail = get_grant_detail(db, grant_id)
    if not detail:
        return HTMLResponse("<h1>404</h1><p>Grant not found.</p>", status_code=404)

    return templates.TemplateResponse(request, "grants/detail.html", {
        "title": detail["grant"].code, "user": user, **detail,
    })