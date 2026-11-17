import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.core.security import hash_token, get_password_hash, verify_password
from app.core.rate_limit import record_login_attempt, check_login_rate_limit
from app.core.config import settings
from app.models.security import UserSession, LoginAttempt
from app.models.user import User
from app.models.audit import AuditLog
from app.models.enums import UserRole
from app.services.audit_service import verify_audit_chain, get_audit_head


@pytest.fixture
def sec_user(db_session):
    user = User(
        email="sec@test.com",
        password_hash=get_password_hash("Secret123!"),
        role=UserRole.SYSTEM_ADMIN,
        is_active=True,
        language="fr",
    )
    db_session.add(user)
    db_session.flush()
    return user


def test_password_hashing_and_token_hashing(sec_user):
    assert verify_password("Secret123!", sec_user.password_hash) is True
    assert verify_password("wrong", sec_user.password_hash) is False

    token = "opaque-token-value"
    digest = hash_token(token)
    assert digest != token
    assert len(digest) == 64
    assert hash_token(token) == digest


def test_session_lookup_and_revocation(db_session, sec_user):
    raw_token = "raw-session-token"
    now = datetime.now(timezone.utc)

    session = UserSession(
        user_id=sec_user.id,
        token_hash=hash_token(raw_token),
        csrf_token="csrf-abc",
        created_at=now,
        expires_at=now + timedelta(days=7),
    )
    db_session.add(session)
    db_session.flush()

    found = db_session.query(UserSession).filter(
        UserSession.token_hash == hash_token(raw_token)
    ).first()
    assert found is not None
    assert found.revoked_at is None
    assert found.expires_at > now

    found.revoked_at = now
    db_session.flush()

    active = db_session.query(UserSession).filter(
        UserSession.token_hash == hash_token(raw_token),
        UserSession.revoked_at.is_(None),
    ).first()
    assert active is None


def test_login_rate_limit_blocks_after_threshold(db_session, sec_user):
    email = "sec@test.com"
    ip = "203.0.113.9"

    check_login_rate_limit(db_session, email, ip)  # must not raise yet

    for _ in range(settings.LOGIN_MAX_ATTEMPTS):
        record_login_attempt(db_session, email, ip, False)

    with pytest.raises(ValueError) as excinfo:
        check_login_rate_limit(db_session, email, ip)

    assert "Too many failed login attempts" in str(excinfo.value)

    # A different IP is unaffected.
    check_login_rate_limit(db_session, email, "198.51.100.1")


def test_audit_hash_chain_is_intact(db_session, sec_user):
    for index in range(3):
        db_session.add(AuditLog(
            user_id=sec_user.id,
            timestamp=datetime.now(timezone.utc),
            ip_address="127.0.0.1",
            entity_type="SecurityTest",
            entity_id=index + 1,
            action="CREATE",
            after_state={"index": index},
        ))
    db_session.flush()

    rows = db_session.query(AuditLog).order_by(AuditLog.id).all()
    for row in rows:
        assert row.row_hash is not None
        assert len(row.row_hash) == 64
        assert row.prev_hash is not None

    assert verify_audit_chain(db_session) == []

    head = get_audit_head(db_session)
    assert head is not None
    assert head["row_hash"] == rows[-1].row_hash


def test_csrf_cookie_reuses_supplied_token():
    """The form token and the cookie value must be identical."""
    from fastapi import Response
    from app.core.security import issue_csrf_cookie, CSRF_COOKIE_NAME

    response = Response()
    token = "explicit-form-token-value"
    returned = issue_csrf_cookie(response, token)

    assert returned == token

    cookies = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]
    matching = [c for c in cookies if c.startswith(f"{CSRF_COOKIE_NAME}=")]
    assert len(matching) == 1
    assert matching[0].split(";")[0] == f"{CSRF_COOKIE_NAME}={token}"


def test_csrf_cookie_generates_token_when_absent():
    from fastapi import Response
    from app.core.security import issue_csrf_cookie, CSRF_COOKIE_NAME

    response = Response()
    token = issue_csrf_cookie(response)

    assert token
    cookies = [
        value.decode("latin-1")
        for name, value in response.raw_headers
        if name.lower() == b"set-cookie"
    ]
    matching = [c for c in cookies if c.startswith(f"{CSRF_COOKIE_NAME}=")]
    assert matching[0].split(";")[0] == f"{CSRF_COOKIE_NAME}={token}"