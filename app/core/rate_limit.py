from datetime import datetime, timedelta, timezone

from sqlalchemy.orm import Session
from sqlalchemy import func, select

from app.core.config import settings
from app.models.security import LoginAttempt


def record_login_attempt(db: Session, email: str, ip_address: str, success: bool) -> None:
    db.add(LoginAttempt(
        email=email.lower().strip()[:255],
        ip_address=ip_address[:45],
        success=success,
        attempted_at=datetime.now(timezone.utc),
    ))
    db.commit()


def check_login_rate_limit(db: Session, email: str, ip_address: str) -> None:
    window_start = datetime.now(timezone.utc) - timedelta(minutes=settings.LOGIN_WINDOW_MINUTES)

    failures = db.execute(
        select(func.count(LoginAttempt.id)).where(
            LoginAttempt.email == email.lower().strip()[:255],
            LoginAttempt.ip_address == ip_address[:45],
            LoginAttempt.success.is_(False),
            LoginAttempt.attempted_at >= window_start,
        )
    ).scalar() or 0

    if failures >= settings.LOGIN_MAX_ATTEMPTS:
        raise ValueError("Too many failed login attempts. Please try again later.")