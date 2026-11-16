from fastapi import APIRouter, Depends, Request, Form, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import get_current_user
from app.models.enums import UserRole
from app.models.user import User
from app.services.settings_service import get_settings, update_settings, SettingsUpdateSchema
from app.core.templates import templates

router = APIRouter(prefix="/settings", tags=["Settings"])


@router.get("/", response_class=HTMLResponse)
async def settings_page(
        request: Request,
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
) -> HTMLResponse:
    if user.role not in [UserRole.SYSTEM_ADMIN, UserRole.FINANCE_MANAGER_APPROVER]:
        raise HTTPException(status_code=403, detail="Forbidden")

    settings = get_settings(db)
    return templates.TemplateResponse("settings/index.html", {
        "request": request,
        "settings": settings,
        "user": user
    })


@router.post("/", response_class=HTMLResponse)
async def update_settings_endpoint(
        request: Request,
        multi_currency_enabled: bool = Form(False),
        donor_fund_tracking_enabled: bool = Form(False),
        project_cost_center_enabled: bool = Form(False),
        budget_control_enabled: bool = Form(False),
        budget_enforcement_mode: str = Form("NONE"),
        maker_checker_approval_enabled: bool = Form(False),
        tax_withholding_enabled: bool = Form(False),
        db: Session = Depends(get_db),
        user: User = Depends(get_current_user)
) -> HTMLResponse:
    if user.role not in [UserRole.SYSTEM_ADMIN, UserRole.FINANCE_MANAGER_APPROVER]:
        raise HTTPException(status_code=403, detail="Forbidden")

    try:
        updates = SettingsUpdateSchema(
            multi_currency_enabled=multi_currency_enabled,
            donor_fund_tracking_enabled=donor_fund_tracking_enabled,
            project_cost_center_enabled=project_cost_center_enabled,
            budget_control_enabled=budget_control_enabled,
            budget_enforcement_mode=budget_enforcement_mode,
            maker_checker_approval_enabled=maker_checker_approval_enabled,
            tax_withholding_enabled=tax_withholding_enabled,
        )
        settings = update_settings(db, updates)
        return templates.TemplateResponse("settings/_settings_form.html", {
            "request": request, "settings": settings, "success": "Paramètres mis à jour avec succès."
        })
    except ValueError as e:
        return templates.TemplateResponse("settings/_settings_form.html", {
            "request": request, "settings": get_settings(db), "error": str(e)
        }, status_code=400)