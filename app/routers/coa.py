from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.services.coa_service import get_coa_tree, create_account, toggle_account_active, AccountCreateSchema
from app.core.templates import templates
from app.models.enums import NormalBalance
from app.models.user import User

router = APIRouter(prefix="/accounting/coa", tags=["Chart of Accounts"])

@router.get("/", response_class=HTMLResponse)
async def coa_page(
    request: Request,
    search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> HTMLResponse:
    accounts = get_coa_tree(db, search)
    return templates.TemplateResponse("accounting/coa.html", {
        "request": request, "accounts": accounts, "search": search
    })

@router.post("/toggle/{account_id}", response_class=HTMLResponse)
async def toggle_account(
    account_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> HTMLResponse:
    account = toggle_account_active(db, account_id)
    return templates.TemplateResponse("accounting/_coa_row.html", {"request": request, "account": account})

@router.post("/create", response_class=HTMLResponse)
async def create_account_endpoint(
    request: Request,
    code: str = Form(...),
    label: str = Form(...),
    account_class: int = Form(...),
    normal_balance: str = Form(...),
    is_postable: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user)
) -> HTMLResponse:
    try:
        new_account = create_account(db, AccountCreateSchema(
            code=code, label=label, account_class=account_class,
            normal_balance=NormalBalance(normal_balance), is_postable=is_postable
        ))
        return templates.TemplateResponse("accounting/_coa_row.html", {"request": request, "account": new_account})
    except Exception as e:
        return templates.TemplateResponse("accounting/_create_form.html", {
            "request": request, "error": str(e)
        }, status_code=400)