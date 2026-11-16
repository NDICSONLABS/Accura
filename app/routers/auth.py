from fastapi import APIRouter, Depends, Form, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import verify_password, set_session, clear_session
from app.models.user import User

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    from app.core.templates import templates
    return templates.TemplateResponse("auth/login.html", {"request": request})


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
        request: Request,
        response: Response,
        email: str = Form(...),
        password: str = Form(...),
        db: Session = Depends(get_db)
):
    # No return type annotation here to prevent FastAPI Pydantic validation errors
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.password_hash):
        from app.core.templates import templates
        return templates.TemplateResponse("auth/login.html", {
            "request": request,
            "error": "Invalid email or password"
        }, status_code=400)

    set_session(response, user.id)
    return RedirectResponse(url="/", status_code=303)


@router.post("/logout")
async def logout(response: Response):
    # No return type annotation here either
    clear_session(response)
    return RedirectResponse(url="/auth/login", status_code=303)