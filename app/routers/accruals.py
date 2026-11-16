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
from app.models.master_data import ThirdParty, AccountingJournal
from app.models.accruals import SupplierBill, TreasurySettlement
from app.models.currency import Currency
from app.services.accrual_service import (
    create_supplier_bill, post_supplier_bill, get_bill_totals,
    list_open_bills, create_settlement, post_settlement, get_settlement_detail,
    SupplierBillCreateSchema, BillLineSchema,
    SettlementCreateSchema, SettlementAllocationSchema,
)

router = APIRouter(prefix="/accruals", tags=["Accruals"])


def _dec(value: str | None, default: str = "0") -> Decimal:
    try:
        return Decimal((value or default).strip() or default)
    except InvalidOperation:
        return Decimal(default)


def _item(values: list[str] | None, index: int) -> str:
    if not values or index >= len(values):
        return ""
    return values[index] or ""


def _opt_int(value: str) -> int | None:
    value = (value or "").strip()
    try:
        return int(value) if value else None
    except ValueError:
        return None


# ------------------------------------------------------------------ BILLS


@router.get("/bills/", response_class=HTMLResponse)
async def bill_list(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bills = db.query(SupplierBill).order_by(SupplierBill.id.desc()).limit(200).all()
    rows = []
    for bill in bills:
        totals = get_bill_totals(db, bill)
        rows.append({
            "bill": bill,
            "supplier": db.get(ThirdParty, bill.third_party_id),
            "totals": totals,
        })

    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(request, "accruals/bills/_bill_rows.html", {"rows": rows})

    return templates.TemplateResponse(request, "accruals/bills/list.html", {
        "title": "Factures Fournisseurs", "rows": rows, "user": user,
    })


@router.get("/bills/new", response_class=HTMLResponse)
async def new_bill_page(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return templates.TemplateResponse(request, "accruals/bills/new.html", {
        "title": "Nouvelle Facture",
        "suppliers": db.query(ThirdParty).order_by(ThirdParty.name).all(),
        "expense_accounts": db.query(Account).filter(Account.account_class == 6, Account.is_postable == True).order_by(Account.code).all(),
        "vat_accounts": db.query(Account).filter(Account.code == "445").all(),
        "currencies": db.query(Currency).order_by(Currency.code).all(),
        "user": user,
    })


@router.post("/bills/create", response_class=HTMLResponse)
async def create_bill_endpoint(
    request: Request,
    third_party_id: int = Form(...),
    bill_date: str = Form(...),
    due_date: str = Form(...),
    reference: str = Form(...),
    description: str = Form(...),
    currency_code: str = Form("XAF"),
    exchange_rate: str = Form("1.000000"),
    withholding_tax_base: str = Form("0"),
    vat_account_code: str | None = Form(default=None),
    account_codes: list[str] = Form(...),
    net_amounts: list[str] | None = Form(default=None),
    vat_amounts: list[str] | None = Form(default=None),
    vat_deductible_flags: list[str] | None = Form(default=None),
    line_descriptions: list[str] | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        lines: list[BillLineSchema] = []
        for index in range(len(account_codes)):
            code = account_codes[index].strip()
            net = _dec(_item(net_amounts, index))
            if not code and net == Decimal("0"):
                continue
            if not code:
                raise ValueError("Every bill line requires an account code.")

            lines.append(BillLineSchema(
                account_code=code,
                base_amount=net,
                vat_amount=_dec(_item(vat_amounts, index)),
                vat_deductible=_item(vat_deductible_flags, index) == "true",
                description=_item(line_descriptions, index).strip() or None,
            ))

        bill = create_supplier_bill(db, user.id, SupplierBillCreateSchema(
            third_party_id=third_party_id,
            bill_date=date.fromisoformat(bill_date),
            due_date=date.fromisoformat(due_date),
            reference=reference,
            description=description,
            currency_code=currency_code,
            exchange_rate=_dec(exchange_rate, "1.000000"),
            withholding_tax_base=_dec(withholding_tax_base),
            vat_account_code=vat_account_code.strip() if vat_account_code and vat_account_code.strip() else None,
            lines=lines,
        ))

        return templates.TemplateResponse(request, "accruals/_feedback.html", {
            "success": "Supplier bill saved as DRAFT.", "bill": bill,
        })
    except ValueError as e:
        return templates.TemplateResponse(request, "accruals/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/bills/{bill_id}", response_class=HTMLResponse)
async def bill_detail(
    bill_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    bill = db.get(SupplierBill, bill_id)
    if not bill:
        return HTMLResponse("<h1>404</h1><p>Bill not found.</p>", status_code=404)

    totals = get_bill_totals(db, bill)
    preview = []
    if bill.status.value == "DRAFT":
        from app.services.accrual_service import build_bill_journal_lines
        preview = build_bill_journal_lines(db, bill)

    return templates.TemplateResponse(request, "accruals/bills/detail.html", {
        "title": bill.reference,
        "bill": bill,
        "supplier": db.get(ThirdParty, bill.third_party_id),
        "totals": totals,
        "preview": preview,
        "user": user,
    })


@router.post("/bills/{bill_id}/post", response_class=HTMLResponse)
async def post_bill_endpoint(
    bill_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        bill = post_supplier_bill(db, bill_id, user.id)
        return templates.TemplateResponse(request, "accruals/_feedback.html", {
            "success": "Supplier bill has been POSTED.", "bill": bill,
        })
    except ValueError as e:
        return templates.TemplateResponse(request, "accruals/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


# ------------------------------------------------------------------ SETTLEMENTS


@router.get("/settlements/new", response_class=HTMLResponse)
async def new_settlement_page(
    request: Request,
    third_party_id: str | None = None,
    currency_code: str = "XAF",
    exchange_rate: str = "1.000000",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    supplier_id = _opt_int(third_party_id or "")
    open_bills = list_open_bills(db, supplier_id) if supplier_id else []

    if open_bills:
        currency_code = open_bills[0]["currency_code"]

    return templates.TemplateResponse(request, "accruals/settlements/new.html", {
        "title": "Règlement Fournisseur",
        "suppliers": db.query(ThirdParty).order_by(ThirdParty.name).all(),
        "treasury_accounts": db.query(Account).filter(Account.account_class == 5, Account.is_postable == True).order_by(Account.code).all(),
        "journals": db.query(AccountingJournal).filter(AccountingJournal.journal_type.in_(["BANK", "CASH"])).all(),
        "open_bills": open_bills,
        "selected_supplier_id": supplier_id,
        "currency_code": currency_code,
        "exchange_rate": exchange_rate,
        "user": user,
    })


@router.post("/settlements/create", response_class=HTMLResponse)
async def create_settlement_endpoint(
    request: Request,
    third_party_id: int = Form(...),
    settlement_date: str = Form(...),
    journal_code: str = Form(...),
    treasury_account_code: str = Form(...),
    reference: str = Form(...),
    description: str = Form(...),
    currency_code: str = Form("XAF"),
    exchange_rate: str = Form("1.000000"),
    bill_ids: list[str] | None = Form(default=None),
    allocated_amounts: list[str] | None = Form(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        allocations: list[SettlementAllocationSchema] = []
        for index in range(len(bill_ids or [])):
            bill_id = _opt_int(_item(bill_ids, index))
            amount = _dec(_item(allocated_amounts, index))
            if bill_id and amount > Decimal("0"):
                allocations.append(SettlementAllocationSchema(
                    bill_id=bill_id, allocated_foreign_amount=amount,
                ))

        settlement = create_settlement(db, user.id, SettlementCreateSchema(
            third_party_id=third_party_id,
            settlement_date=date.fromisoformat(settlement_date),
            journal_code=journal_code,
            treasury_account_code=treasury_account_code,
            reference=reference,
            description=description,
            currency_code=currency_code,
            exchange_rate=_dec(exchange_rate, "1.000000"),
            allocations=allocations,
        ))

        return templates.TemplateResponse(request, "accruals/_feedback.html", {
            "success": "Settlement saved as DRAFT.", "settlement": settlement,
        })
    except ValueError as e:
        return templates.TemplateResponse(request, "accruals/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)


@router.get("/settlements/{settlement_id}", response_class=HTMLResponse)
async def settlement_detail(
    settlement_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    detail = get_settlement_detail(db, settlement_id)
    if not detail:
        return HTMLResponse("<h1>404</h1><p>Settlement not found.</p>", status_code=404)

    return templates.TemplateResponse(request, "accruals/settlements/detail.html", {
        "title": detail["settlement"].reference, "user": user, **detail,
    })


@router.post("/settlements/{settlement_id}/post", response_class=HTMLResponse)
async def post_settlement_endpoint(
    settlement_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    try:
        settlement = post_settlement(db, settlement_id, user.id)
        return templates.TemplateResponse(request, "accruals/_feedback.html", {
            "success": "Settlement has been POSTED.", "settlement": settlement,
        })
    except ValueError as e:
        return templates.TemplateResponse(request, "accruals/_feedback.html",
            {"error": translate_message(request, str(e))}, status_code=400)