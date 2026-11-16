from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.services.coa_service import (
    get_coa_tree,
    create_account,
    toggle_account_active,
    AccountCreateSchema,
)
from app.models.enums import NormalBalance
from app.models.user import User

router = APIRouter(prefix="/accounting/coa", tags=["Chart of Accounts"])


@router.get("/", response_class=HTMLResponse)
async def coa_page(
    request: Request,
    search: str = "",
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    accounts = get_coa_tree(db, search)

    # HTMX search should return only the table rows partial.
    if request.headers.get("HX-Request"):
        return templates.TemplateResponse(
            request,
            "accounting/_coa_rows.html",
            {
                "accounts": accounts,
                "search": search,
            },
        )

    return templates.TemplateResponse(
        request,
        "accounting/coa.html",
        {
            "title": "Plan Comptable",
            "accounts": accounts,
            "search": search,
            "user": user,
        },
    )


@router.post("/toggle/{account_id}", response_class=HTMLResponse)
async def toggle_account(
    account_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    account = toggle_account_active(db, account_id)

    return templates.TemplateResponse(
        request,
        "accounting/_coa_row.html",
        {
            "account": account,
        },
    )


@router.post("/create", response_class=HTMLResponse)
async def create_account_endpoint(
    request: Request,
    code: str = Form(...),
    label: str = Form(...),
    account_class: int = Form(...),
    normal_balance: str = Form(...),
    is_postable: bool = Form(False),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    from app.core.i18n import translate_message

    try:
        new_account = create_account(
            db,
            AccountCreateSchema(
                code=code,
                label=label,
                account_class=account_class,
                normal_balance=NormalBalance(normal_balance),
                is_postable=is_postable,
            ),
        )

        return templates.TemplateResponse(
            request,
            "accounting/_coa_row.html",
            {"account": new_account},
        )
    except Exception as e:
        return HTMLResponse(
            f"<div class='text-red-600 p-2 font-medium'>{translate_message(request, str(e))}</div>",
            status_code=400,
        )