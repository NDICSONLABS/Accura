import hashlib
import secrets
from datetime import datetime, timedelta, timezone

from passlib.context import CryptContext
from fastapi import Response, Request, HTTPException, Depends
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models.user import User
from app.models.enums import UserRole
from app.models.security import UserSession

pwd_context = CryptContext(schemes=["argon2"], deprecated="auto")

SESSION_COOKIE_NAME = settings.SESSION_COOKIE_NAME
CSRF_COOKIE_NAME = settings.CSRF_COOKIE_NAME
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}
CSRF_EXEMPT_PATHS = {"/healthz"}


def verify_password(plain_password: str, hashed_password: str) -> bool:
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    return pwd_context.hash(password)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def client_ip(request: Request) -> str:
    forwarded = request.headers.get("x-forwarded-for")
    if forwarded:
        return forwarded.split(",")[0].strip()[:45]
    return (request.client.host if request.client else "unknown")[:45]


def create_session(db: Session, response: Response, request: Request, user_id: int) -> UserSession:
    raw_token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)

    session = UserSession(
        user_id=user_id,
        token_hash=hash_token(raw_token),
        csrf_token=csrf_token,
        ip_address=client_ip(request),
        user_agent=(request.headers.get("user-agent") or "")[:255],
        created_at=now,
        expires_at=now + timedelta(days=settings.SESSION_TTL_DAYS),
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    max_age = settings.SESSION_TTL_DAYS * 86400
    response.set_cookie(
        SESSION_COOKIE_NAME, raw_token,
        max_age=max_age, httponly=True, samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE, path="/",
    )
    response.set_cookie(
        CSRF_COOKIE_NAME, csrf_token,
        max_age=max_age, httponly=False, samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE, path="/",
    )
    return session


def get_session(db: Session, request: Request) -> UserSession | None:
    raw_token = request.cookies.get(SESSION_COOKIE_NAME)
    if not raw_token:
        return None

    session = (
        db.query(UserSession)
        .filter(UserSession.token_hash == hash_token(raw_token))
        .first()
    )
    if not session:
        return None
    if session.revoked_at is not None:
        return None
    if session.expires_at <= datetime.now(timezone.utc):
        return None
    return session


def destroy_session(db: Session, response: Response, request: Request) -> None:
    session = get_session(db, request)
    if session:
        session.revoked_at = datetime.now(timezone.utc)
        db.commit()
    response.delete_cookie(SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(CSRF_COOKIE_NAME, path="/")


def issue_csrf_cookie(response: Response, token: str | None = None) -> str:
    """
    Issue a CSRF cookie. If `token` is supplied, reuse it so the rendered
    form field and the cookie are guaranteed to be identical.
    """
    value = token or secrets.token_urlsafe(32)
    response.set_cookie(
        CSRF_COOKIE_NAME, value,
        max_age=7200, httponly=False, samesite="lax",
        secure=settings.SESSION_COOKIE_SECURE, path="/",
    )
    return value


def get_current_user(request: Request, db: Session = Depends(get_db)) -> User:
    session = get_session(db, request)
    if not session:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user = db.get(User, session.user_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="User not found")
    return user


def require_role(*allowed_roles: UserRole):
    def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(status_code=403, detail="Insufficient permissions")
        return current_user
    return role_checker


async def csrf_protect(request: Request, db: Session = Depends(get_db)) -> None:
    if request.method in SAFE_METHODS:
        return
    if request.url.path in CSRF_EXEMPT_PATHS:
        return

    token = request.headers.get("X-CSRF-Token")
    if not token:
        content_type = request.headers.get("content-type", "")
        if "application/x-www-form-urlencoded" in content_type or "multipart/form-data" in content_type:
            form = await request.form()
            token = form.get("csrf_token")

    session = get_session(db, request)
    expected = session.csrf_token if session else request.cookies.get(CSRF_COOKIE_NAME)

    if not token or not expected or not secrets.compare_digest(str(token), str(expected)):
        raise HTTPException(status_code=403, detail="CSRF validation failed")