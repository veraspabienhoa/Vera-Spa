"""Report safe production data-source counts without exposing credentials.

The VPS deploy user does not necessarily inherit the API service environment.
This check reuses only the DB_* variables from the running Web V2 API process,
then prints aggregate row counts for deployment verification.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL


API_MARKER = "vera_web_v2_api_v38:app"
SAFE_ENV_KEYS = {
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "DB_POOL_SIZE",
    "DB_MAX_OVERFLOW",
    "DB_CONNECT_TIMEOUT",
    "DB_SSLMODE",
}
TABLES = (
    "employees",
    "leave_records",
    "payroll_history_rows",
    "vera_dataset_cache",
    "vera_primary_dataset",
    "vera_source_row",
)


def _running_api_environment(proc_root: Path = Path("/proc")) -> dict[str, str]:
    for process_dir in proc_root.iterdir():
        if not process_dir.name.isdigit():
            continue
        try:
            command = (process_dir / "cmdline").read_bytes().replace(b"\0", b" ").decode("utf-8", "replace")
            if API_MARKER not in command:
                continue
            entries = (process_dir / "environ").read_bytes().split(b"\0")
        except (FileNotFoundError, PermissionError, ProcessLookupError):
            continue
        environment: dict[str, str] = {}
        for entry in entries:
            key, separator, value = entry.partition(b"=")
            decoded_key = key.decode("utf-8", "replace")
            if separator and decoded_key in SAFE_ENV_KEYS:
                environment[decoded_key] = value.decode("utf-8", "replace")
        if environment:
            return environment
    return {}


def _database_url(environment: dict[str, str]) -> URL:
    missing = [key for key in ("DB_HOST", "DB_USER", "DB_PASS") if not environment.get(key)]
    if missing:
        raise RuntimeError("API process is missing database settings: " + ", ".join(missing))
    return URL.create(
        "postgresql+psycopg",
        username=environment["DB_USER"],
        password=environment["DB_PASS"],
        host=environment["DB_HOST"],
        port=int(environment.get("DB_PORT", "5432")),
        database=environment.get("DB_NAME", "postgres"),
    )


def main() -> None:
    environment = _running_api_environment()
    if not environment:
        raise SystemExit("DATA CHECK FAILED: running Web V2 API process was not found or is not readable")

    engine = create_engine(
        _database_url(environment),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": max(3, int(environment.get("DB_CONNECT_TIMEOUT", "10"))),
            "sslmode": environment.get("DB_SSLMODE", "require").strip() or "require",
        },
    )
    existing = set(inspect(engine).get_table_names())
    counts: dict[str, int | None] = {}
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
        for table in TABLES:
            counts[table] = (
                int(connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
                if table in existing
                else None
            )

    print("DATA CHECK: database connection OK")
    for table, count in counts.items():
        print(f"DATA CHECK: {table}={'missing' if count is None else count}")
    if not any((count or 0) > 0 for count in counts.values()):
        raise SystemExit("DATA CHECK FAILED: production database contains no application rows")


if __name__ == "__main__":
    main()
