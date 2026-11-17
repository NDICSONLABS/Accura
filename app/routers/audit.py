from fastapi import APIRouter, Depends, Request, Query
from fastapi.responses import HTMLResponse, JSONResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import require_role
from app.core.templates import templates
from app.models.user import User
from app.models.enums import UserRole
from app.models.audit import AuditLog
from app.services.audit_service import verify_audit_chain, get_audit_head

router = APIRouter(prefix="/audit", tags=["Audit Trail"])


@router.get("/trail", response_class=HTMLResponse)
async def audit_trail_page(
    request: Request,
    limit: int = Query(50, le=200),
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.AUDITOR_VIEWER, UserRole.SYSTEM_ADMIN)),
):
    logs = (
        db.query(AuditLog, User.email)
        .outerjoin(User, AuditLog.user_id == User.id)
        .order_by(AuditLog.timestamp.desc())
        .limit(limit)
        .all()
    )

    return templates.TemplateResponse(request, "audit/trail.html", {
        "title": "Journal d'Audit",
        "logs": logs,
        "broken_rows": verify_audit_chain(db),
        "head": get_audit_head(db),
        "user": user,
    })


@router.get("/verify")
async def audit_verify(
    db: Session = Depends(get_db),
    user: User = Depends(require_role(UserRole.AUDITOR_VIEWER, UserRole.SYSTEM_ADMIN)),
):
    broken = verify_audit_chain(db)
    return JSONResponse({
        "intact": len(broken) == 0,
        "broken_rows": broken,
        "head": get_audit_head(db),
    })