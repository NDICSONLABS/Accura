"""PostgreSQL restore. Usage: python scripts/restore_db.py <dump_file>"""
import os
import subprocess
import sys
from pathlib import Path
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("Usage: python scripts/restore_db.py <dump_file>")

    dump = Path(sys.argv[1]).resolve()
    if not dump.exists():
        raise SystemExit(f"Dump not found: {dump}")

    confirm = input(f"This will OVERWRITE database. Type RESTORE to continue: ")
    if confirm != "RESTORE":
        raise SystemExit("Aborted.")

    url = urlparse(settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = unquote(url.password)

    cmd = [
        "pg_restore",
        "--host", url.hostname or "localhost",
        "--port", str(url.port or 5432),
        "--username", unquote(url.username or "postgres"),
        "--dbname", url.path.lstrip("/"),
        "--clean", "--if-exists", "--no-owner",
        str(dump),
    ]

    subprocess.run(cmd, env=env, check=True)
    print("Restore complete. Run: alembic upgrade head")


if __name__ == "__main__":
    main()