"""production hardening: sessions, rate limits, audit hash chain

Revision ID: 012
Revises: 011
Create Date: 2026-11-17 20:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "012"
down_revision: Union[str, None] = "011"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "user_sessions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("csrf_token", sa.String(64), nullable=False),
        sa.Column("ip_address", sa.String(45)),
        sa.Column("user_agent", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_user_sessions_token_hash", "user_sessions", ["token_hash"])

    op.create_table(
        "login_attempts",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("ip_address", sa.String(45), nullable=False),
        sa.Column("success", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("attempted_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_login_attempts_lookup", "login_attempts", ["email", "ip_address", "attempted_at"])

    op.add_column("audit_log", sa.Column("prev_hash", sa.String(64)))
    op.add_column("audit_log", sa.Column("row_hash", sa.String(64)))

    # Backfill must bypass the append-only trigger.
    op.execute("ALTER TABLE audit_log DISABLE TRIGGER ALL;")

    op.execute("""
        DO $$
        DECLARE
            r RECORD;
            prev TEXT := repeat('0', 64);
            payload TEXT;
        BEGIN
            FOR r IN SELECT * FROM audit_log ORDER BY id LOOP
                payload := prev || '|' || COALESCE(r.user_id::text, '') || '|'
                        || r.timestamp::text || '|' || COALESCE(r.ip_address, '') || '|'
                        || r.entity_type || '|' || r.entity_id::text || '|' || r.action || '|'
                        || COALESCE(r.before_state::text, '') || '|'
                        || COALESCE(r.after_state::text, '');
                UPDATE audit_log
                SET prev_hash = prev,
                    row_hash = encode(sha256(convert_to(payload, 'UTF8')), 'hex')
                WHERE id = r.id;
                prev := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
            END LOOP;
        END $$;
    """)

    op.execute("ALTER TABLE audit_log ENABLE TRIGGER ALL;")

    op.execute("""
        CREATE OR REPLACE FUNCTION audit_hash_chain() RETURNS TRIGGER AS $$
        DECLARE
            prev TEXT;
            payload TEXT;
        BEGIN
            -- Serialize chain writes so concurrent inserts cannot fork the chain.
            PERFORM pg_advisory_xact_lock(hashtext('audit_log_chain'));

            SELECT row_hash INTO prev FROM audit_log ORDER BY id DESC LIMIT 1;
            prev := COALESCE(prev, repeat('0', 64));

            NEW.prev_hash := prev;
            NEW.timestamp := COALESCE(NEW.timestamp, NOW());

            payload := prev || '|' || COALESCE(NEW.user_id::text, '') || '|'
                    || NEW.timestamp::text || '|' || COALESCE(NEW.ip_address, '') || '|'
                    || NEW.entity_type || '|' || NEW.entity_id::text || '|' || NEW.action || '|'
                    || COALESCE(NEW.before_state::text, '') || '|'
                    || COALESCE(NEW.after_state::text, '');

            NEW.row_hash := encode(sha256(convert_to(payload, 'UTF8')), 'hex');
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)

    op.execute("""
        CREATE TRIGGER trg_audit_hash_chain
        BEFORE INSERT ON audit_log
        FOR EACH ROW EXECUTE FUNCTION audit_hash_chain();
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION audit_chain_broken_rows()
        RETURNS TABLE(broken_id bigint, reason text) AS $$
        DECLARE
            r RECORD;
            prev TEXT := repeat('0', 64);
            payload TEXT;
            expected TEXT;
        BEGIN
            FOR r IN SELECT * FROM audit_log ORDER BY id LOOP
                IF r.prev_hash IS DISTINCT FROM prev THEN
                    broken_id := r.id; reason := 'prev_hash mismatch'; RETURN NEXT;
                END IF;

                payload := prev || '|' || COALESCE(r.user_id::text, '') || '|'
                        || r.timestamp::text || '|' || COALESCE(r.ip_address, '') || '|'
                        || r.entity_type || '|' || r.entity_id::text || '|' || r.action || '|'
                        || COALESCE(r.before_state::text, '') || '|'
                        || COALESCE(r.after_state::text, '');
                expected := encode(sha256(convert_to(payload, 'UTF8')), 'hex');

                IF r.row_hash IS DISTINCT FROM expected THEN
                    broken_id := r.id; reason := 'row_hash mismatch'; RETURN NEXT;
                END IF;

                prev := r.row_hash;
            END LOOP;
        END;
        $$ LANGUAGE plpgsql;
    """)


def downgrade() -> None:
    op.execute("DROP TRIGGER IF EXISTS trg_audit_hash_chain ON audit_log;")
    op.execute("DROP FUNCTION IF EXISTS audit_hash_chain();")
    op.execute("DROP FUNCTION IF EXISTS audit_chain_broken_rows();")
    op.drop_column("audit_log", "row_hash")
    op.drop_column("audit_log", "prev_hash")
    op.drop_index("ix_login_attempts_lookup", table_name="login_attempts")
    op.drop_table("login_attempts")
    op.drop_index("ix_user_sessions_token_hash", table_name="user_sessions")
    op.drop_table("user_sessions")