import secrets

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import (
    verify_password, create_session, destroy_session,
    issue_csrf_cookie, client_ip,
)
from app.core.rate_limit import check_login_rate_limit, record_login_attempt
from app.core.templates import templates
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


def _render_login(request: Request, error: str | None = None, status_code: int = 200):
    """
    Mint ONE token, render it into the form, and set the cookie to the SAME value.
    This is the only correct ordering — rendering before issuing causes a mismatch.
    """
    token = secrets.token_urlsafe(32)
    context = {"csrf_token": token}
    if error:
        context["error"] = error

    response = templates.TemplateResponse(request, "auth/login.html", context, status_code=status_code)
    issue_csrf_cookie(response, token)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return _render_login(request)


@router.post("/login")
async def login_submit(
    request: Request,
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    ip = client_ip(request)

    try:
        check_login_rate_limit(db, email, ip)
    except ValueError as e:
        record_login_attempt(db, email, ip, False)
        return _render_login(request, error=str(e), status_code=429)

    user = db.query(User).filter(User.email == email.lower().strip()).first()
    if not user or not user.is_active or not verify_password(password, user.password_hash):
        record_login_attempt(db, email, ip, False)
        return _render_login(request, error="Invalid email or password", status_code=400)

    record_login_attempt(db, email, ip, True)

    redirect_response = RedirectResponse(url="/", status_code=303)
    create_session(db, redirect_response, request, user.id)
    return redirect_response


@router.post("/logout")
async def logout(request: Request, db: Session = Depends(get_db)):
    redirect_response = RedirectResponse(url="/auth/login", status_code=303)
    destroy_session(db, redirect_response, request)
    return redirect_response