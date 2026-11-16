from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import require_role
from app.core.templates import templates
from app.models.user import User
from app.models.enums import UserRole
from app.models.audit import AuditLog
from app.models.user import User as UserModel

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("/trail", response_class=HTMLResponse)
async def audit_trail_page(
        request: Request,
        limit: int = Query(50, le=200),
        db: Session = Depends(get_db),
        user: User = Depends(require_role(UserRole.AUDITOR_VIEWER, UserRole.SYSTEM_ADMIN))
):
    logs = (
        db.query(AuditLog, UserModel.email)
        .outerjoin(UserModel, AuditLog.user_id == UserModel.id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    return templates.TemplateResponse(request, "audit/trail.html", {
        "title": "Journal d'Audit",
        "logs": logs,
        "user": user,
    })