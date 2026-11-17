"""PostgreSQL backup. Usage: python scripts/backup_db.py [output_dir]"""
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse, unquote

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.core.config import settings  # noqa: E402


def main() -> None:
    url = urlparse(settings.DATABASE_URL.replace("postgresql+psycopg://", "postgresql://"))
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "backups").resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    target = out_dir / f"{url.path.lstrip('/')}_{stamp}.dump"

    env = os.environ.copy()
    if url.password:
        env["PGPASSWORD"] = unquote(url.password)

    cmd = [
        "pg_dump",
        "--host", url.hostname or "localhost",
        "--port", str(url.port or 5432),
        "--username", unquote(url.username or "postgres"),
        "--format", "custom",
        "--no-owner",
        "--file", str(target),
        url.path.lstrip("/"),
    ]

    subprocess.run(cmd, env=env, check=True)
    print(f"Backup written: {target}")


if __name__ == "__main__":
    main()