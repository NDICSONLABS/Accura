from sqlalchemy.orm import Session
from sqlalchemy import text


def verify_audit_chain(db: Session) -> list[dict]:
    rows = db.execute(text("SELECT broken_id, reason FROM audit_chain_broken_rows()")).all()
    return [{"id": row.broken_id, "reason": row.reason} for row in rows]


def get_audit_head(db: Session) -> dict | None:
    row = db.execute(text(
        "SELECT id, row_hash, timestamp FROM audit_log ORDER BY id DESC LIMIT 1"
    )).first()
    if not row:
        return None
    return {"id": row.id, "row_hash": row.row_hash, "timestamp": row.timestamp}