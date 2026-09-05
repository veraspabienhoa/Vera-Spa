"""Report safe production data-source counts without exposing credentials.

The check prefers the same private managed file loaded by the API.  It falls
back to the process's initial environment for deployments that have not adopted
that file yet, then prints only aggregate verification results.
"""
from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.engine import URL

from vera_web_v2_local_auth import local_auth_enabled
from vera_web_v2_runtime_env import RUNTIME_ENV_KEYS, load_managed_runtime_environment


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
    "VERA_AUTH_PROVIDER",
}
TABLES = (
    "employees",
    "leave_records",
    "payroll_history_rows",
    "vera_dataset_cache",
    "vera_primary_dataset",
    "vera_app_setting",
)
LOCAL_AUTH_STORE_TABLE = "vera_app_setting"
LOCAL_AUTH_COLUMNS = {
    "category",
    "setting_key",
    "value_json",
    "source",
    "updated_by",
    "revision",
    "created_at",
    "updated_at",
}


def _running_api_environment(proc_root: Path = Path("/proc")) -> dict[str, str]:
    process_dirs = sorted(
        (path for path in proc_root.iterdir() if path.name.isdigit()),
        key=lambda path: int(path.name),
        reverse=True,
    )
    for process_dir in process_dirs:
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
    managed_environment_loaded = load_managed_runtime_environment()
    environment = (
        {key: os.environ.get(key, "") for key in RUNTIME_ENV_KEYS}
        if managed_environment_loaded
        else _running_api_environment()
    )
    if not environment:
        raise SystemExit("DATA CHECK FAILED: managed settings and running API environment are unavailable")

    sslmode = environment.get("DB_SSLMODE", "require").strip().lower() or "require"
    if sslmode not in {"require", "verify-ca", "verify-full"}:
        sslmode = "require"
    engine = create_engine(
        _database_url(environment),
        pool_pre_ping=True,
        connect_args={
            "connect_timeout": max(3, int(environment.get("DB_CONNECT_TIMEOUT", "10"))),
            "sslmode": sslmode,
        },
    )
    inspector = inspect(engine)
    existing = set(inspector.get_table_names())
    if not local_auth_enabled():
        raise SystemExit("DATA CHECK FAILED: PostgreSQL local Auth is not active")
    if LOCAL_AUTH_STORE_TABLE not in existing:
        raise SystemExit(f"DATA CHECK FAILED: missing {LOCAL_AUTH_STORE_TABLE}")
    auth_columns = {str(item["name"]) for item in inspector.get_columns(LOCAL_AUTH_STORE_TABLE)}
    missing_auth_columns = sorted(LOCAL_AUTH_COLUMNS - auth_columns)
    if missing_auth_columns:
        raise SystemExit(
            "DATA CHECK FAILED: local Auth schema is incomplete: " + ", ".join(missing_auth_columns)
        )
    counts: dict[str, int | None] = {}
    with engine.connect() as connection:
        connection.execute(text("SELECT 1")).scalar_one()
        if not bool(connection.execute(
            text("SELECT has_schema_privilege(current_user, 'public', 'USAGE')")
        ).scalar_one()):
            raise SystemExit("DATA CHECK FAILED: runtime role lacks USAGE on schema public")
        privileges = connection.execute(text("""
            SELECT
              has_table_privilege(current_user, 'public.vera_app_setting', 'SELECT'),
              has_table_privilege(current_user, 'public.vera_app_setting', 'INSERT'),
              has_table_privilege(current_user, 'public.vera_app_setting', 'UPDATE'),
              has_table_privilege(current_user, 'public.vera_app_setting', 'DELETE')
        """)).one()
        if not all(bool(item) for item in privileges):
            raise SystemExit("DATA CHECK FAILED: runtime role lacks CRUD access to vera_app_setting")
        eligible_accounts = int(connection.execute(text("""
            SELECT COUNT(*)
            FROM employees e
            WHERE COALESCE(e.login_locked, false)=false
              AND COALESCE(e.password_value, '') <> ''
              AND COALESCE(e.payload->>'__deleted', 'false') <> 'true'
              AND COALESCE(
                    e.payload->>'Trạng thái làm việc',
                    e.payload->>'employment_status',
                    'Đang làm việc'
                  ) = 'Đang làm việc'
        """)).scalar_one())
        admin_accounts = int(connection.execute(text("""
            SELECT COUNT(*)
            FROM employees e
            WHERE lower(btrim(e.username))='admin'
              AND COALESCE(e.login_locked, false)=false
              AND COALESCE(e.password_value, '') <> ''
              AND lower(COALESCE(e.role, ''))='admin'
              AND COALESCE(e.payload->>'__deleted', 'false') <> 'true'
              AND COALESCE(
                    e.payload->>'Trạng thái làm việc',
                    e.payload->>'employment_status',
                    'Đang làm việc'
                  ) = 'Đang làm việc'
        """)).scalar_one())
        for table in TABLES:
            counts[table] = (
                int(connection.execute(text(f'SELECT COUNT(*) FROM "{table}"')).scalar_one())
                if table in existing
                else None
            )

    print("DATA CHECK: database connection OK")
    print("DATA CHECK: auth_provider=local")
    print("DATA CHECK: local_auth_store=vera_app_setting namespaces ready")
    print(f"DATA CHECK: eligible_local_auth_accounts={eligible_accounts}")
    print("DATA CHECK: local_auth_admin=ready" if admin_accounts == 1 else "DATA CHECK: local_auth_admin=invalid")
    for table, count in counts.items():
        print(f"DATA CHECK: {table}={'missing' if count is None else count}")
    if not any((count or 0) > 0 for count in counts.values()):
        raise SystemExit("DATA CHECK FAILED: production database contains no application rows")
    if eligible_accounts < 1:
        raise SystemExit("DATA CHECK FAILED: no active employee account is eligible for local Auth")
    if admin_accounts != 1:
        raise SystemExit("DATA CHECK FAILED: the active local Auth admin employee is missing or duplicated")


if __name__ == "__main__":
    main()
