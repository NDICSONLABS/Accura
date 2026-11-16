from passlib.context import CryptContext
from fastapi import Response, Request, HTTPException, status, Depends
from sqlalchemy.orm import Session
from app.models.user import User
from app.models.enums import UserRole
from app.core.database import get_db
import secrets

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")
SESSION_COOKIE_NAME = "ngosys_session"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def set_session(response: Response, user_id: int):
    session_token = secrets.token_urlsafe(32)
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=f"{user_id}:{session_token}",
        httponly=True,
        max_age=86400 * 7,
        samesite="lax",
        path="/"  # CRITICAL: Ensures cookie is sent on ALL routes
    )


def clear_session(response: Response):
    response.delete_cookie(key=SESSION_COOKIE_NAME, path="/")


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    cookie = request.cookies.get(SESSION_COOKIE_NAME)
    if not cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")

    try:
        user_id_str, _ = cookie.split(":", 1)
        user = db.query(User).filter(User.id == int(user_id_str), User.is_active == True).first()
    except (ValueError, AttributeError):
        raise HTTPException(status_code=401, detail="Invalid session")

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def require_role(*allowed_roles: UserRole):
    def role_checker(current_user: User = Depends(get_current_user)):
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user

    return role_checker