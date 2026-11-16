from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, set_session, clear_session
from app.models.user import User
from app.core.templates import templates

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "auth/login.html", {})


@router.post("/login")
async def login_submit(
        request: Request,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db)
):
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        return templates.TemplateResponse(request, "auth/login.html", {
            "error": "Email ou mot de passe invalide"
        }, status_code=400)

    # 1. Create the redirect response FIRST
    redirect_response = RedirectResponse(url="/", status_code=303)

    # 2. Set the cookie DIRECTLY on the redirect response
    set_session(redirect_response, user.id)

    # 3. Return it
    return redirect_response


@router.post("/logout")
async def logout():
    # Same fix here for logout
    redirect_response = RedirectResponse(url="/auth/login", status_code=303)
    clear_session(redirect_response)
    return redirect_response