from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.master_data import ThirdParty  # ThirdParty is here
from app.models.account import Account  # Account is here
from app.services.accrual_service import create_supplier_bill, SupplierBillCreateSchema, BillLineSchema
from decimal import Decimal

router = APIRouter(prefix="/accruals", tags=["Accruals"])


@router.get("/bills/new", response_class=HTMLResponse)
async def new_bill_page(request: Request, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    suppliers = db.query(ThirdParty).all()
    expense_accounts = db.query(Account).filter(Account.account_class == 6, Account.is_postable == True).all()
    return templates.TemplateResponse(request, "accruals/bills/new.html", {
        "suppliers": suppliers, "expense_accounts": expense_accounts
    })


@router.post("/bills/preview", response_class=HTMLResponse)
async def preview_bill_gl(
        request: Request,
        supplier_id: int = Form(...),
        total_base: Decimal = Form(...),
        withholding_tax: Decimal = Form(Decimal("0")),
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
):
    # Calculate GL impact for the preview drawer
    net_payable = total_base - withholding_tax
    supplier = db.query(ThirdParty).filter(ThirdParty.id == supplier_id).first()

    return templates.TemplateResponse(request, "accruals/bills/_gl_preview.html", {
        "total_base": total_base,
        "withholding_tax": withholding_tax,
        "net_payable": net_payable,
        "supplier_name": supplier.name if supplier else "Unknown"
    })