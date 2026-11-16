from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, StreamingResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import get_current_user
from app.core.templates import templates
from app.models.user import User
from app.models.period import FiscalYear
from app.models.master_data import Fund
from app.services.statements_service import (
    get_compte_de_resultat,
    get_bilan,
    get_aged_balance,
)
from app.services.export_service import (
    export_compte_resultat_to_excel,
    export_compte_resultat_to_pdf,
    export_bilan_to_excel,
    export_bilan_to_pdf,
    export_aged_balance_to_excel,
    export_aged_balance_to_pdf,
)

router = APIRouter(prefix="/statements", tags=["Financial Statements"])


@router.get("/compte-resultat", response_class=HTMLResponse)
async def compte_resultat_page(
    request: Request,
    fy_id: int = Query(...),
    fund_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = get_compte_de_resultat(db, fy_id, fund_id, project_id)
    fiscal_years = db.query(FiscalYear).all()
    funds = db.query(Fund).all()

    return templates.TemplateResponse(
        request,
        "statements/compte_resultat.html",
        {
            "title": "Compte de Résultat",
            "data": data,
            "fiscal_years": fiscal_years,
            "funds": funds,
            "fy_id": fy_id,
            "fund_id": fund_id,
            "project_id": project_id,
            "user": user,
        },
    )


@router.get("/bilan", response_class=HTMLResponse)
async def bilan_page(
    request: Request,
    fy_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = get_bilan(db, fy_id)
    fiscal_years = db.query(FiscalYear).all()

    return templates.TemplateResponse(
        request,
        "statements/bilan.html",
        {
            "title": "Bilan SYCEBNL",
            "data": data,
            "fiscal_years": fiscal_years,
            "fy_id": fy_id,
            "user": user,
        },
    )


@router.get("/aged-balance", response_class=HTMLResponse)
async def aged_balance_page(
    request: Request,
    balance_type: str = Query("payable"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    is_payable = balance_type == "payable"
    rows = get_aged_balance(db, is_payable=is_payable)

    return templates.TemplateResponse(
        request,
        "statements/aged_balance.html",
        {
            "title": "Balance Âgée des Tiers",
            "rows": rows,
            "balance_type": balance_type,
            "user": user,
        },
    )


@router.get("/exports/compte-resultat.xlsx")
async def export_cr_xlsx(
    fy_id: int = Query(...),
    fund_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = get_compte_de_resultat(db, fy_id, fund_id, project_id)
    buffer = export_compte_resultat_to_excel(data)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=compte_resultat.xlsx"},
    )


@router.get("/exports/compte-resultat.pdf")
async def export_cr_pdf(
    fy_id: int = Query(...),
    fund_id: int | None = None,
    project_id: int | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = get_compte_de_resultat(db, fy_id, fund_id, project_id)
    buffer = export_compte_resultat_to_pdf(data)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=compte_resultat.pdf"},
    )


@router.get("/exports/bilan.xlsx")
async def export_bilan_xlsx(
    fy_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = get_bilan(db, fy_id)
    buffer = export_bilan_to_excel(data)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=bilan_sycebnl.xlsx"},
    )


@router.get("/exports/bilan.pdf")
async def export_bilan_pdf(
    fy_id: int = Query(...),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    data = get_bilan(db, fy_id)
    buffer = export_bilan_to_pdf(data)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=bilan_sycebnl.pdf"},
    )


@router.get("/exports/aged-balance.xlsx")
async def export_aged_balance_xlsx(
    balance_type: str = Query("payable"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    is_payable = balance_type == "payable"
    rows = get_aged_balance(db, is_payable=is_payable)
    title = "Balance Âgée Fournisseurs" if is_payable else "Balance Âgée Clients"
    buffer = export_aged_balance_to_excel(rows, title)

    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=balance_agee.xlsx"},
    )


@router.get("/exports/aged-balance.pdf")
async def export_aged_balance_pdf(
    balance_type: str = Query("payable"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    is_payable = balance_type == "payable"
    rows = get_aged_balance(db, is_payable=is_payable)
    title = "Balance Âgée Fournisseurs" if is_payable else "Balance Âgée Clients"
    buffer = export_aged_balance_to_pdf(rows, title)

    return StreamingResponse(
        buffer,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=balance_agee.pdf"},
    )