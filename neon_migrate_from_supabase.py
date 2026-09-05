"""One-shot PostgreSQL migration runner: Supabase -> Neon test branch.

This job is intentionally guarded:
- source is read-only (pg_dump + SELECT validation only)
- target must not already contain VERA public tables
- only the public schema is migrated; Neon Auth schemas are left untouched
- row counts are validated after restore

Expected env vars:
  DB_HOST DB_PORT DB_NAME DB_USER DB_PASS
  NEON_DB_HOST NEON_DB_PORT NEON_DB_NAME NEON_DB_USER
Optional:
  NEON_DB_SSLMODE (default require)
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
from pathlib import Path

import psycopg


def required(name: str) -> str:
    value = str(os.getenv(name) or "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


def conn_kwargs(prefix: str = "") -> dict:
    if prefix:
        return {
            "host": required(f"{prefix}DB_HOST"),
            "port": int(os.getenv(f"{prefix}DB_PORT", "5432")),
            "dbname": required(f"{prefix}DB_NAME"),
            "user": required(f"{prefix}DB_USER"),
            "sslmode": os.getenv(f"{prefix}DB_SSLMODE", "require"),
            "connect_timeout": 15,
        }
    return {
        "host": required("DB_HOST"),
        "port": int(os.getenv("DB_PORT", "5432")),
        "dbname": required("DB_NAME"),
        "user": required("DB_USER"),
        "password": required("DB_PASS"),
        "sslmode": os.getenv("DB_SSLMODE", "require"),
        "connect_timeout": 15,
    }


def table_counts(conn) -> dict[str, int]:
    rows = conn.execute(
        """
        SELECT tablename
        FROM pg_tables
        WHERE schemaname='public'
        ORDER BY tablename
        """
    ).fetchall()
    output: dict[str, int] = {}
    for (table,) in rows:
        safe = str(table).replace('"', '""')
        output[str(table)] = int(conn.execute(f'SELECT count(*) FROM public."{safe}"').fetchone()[0])
    return output


def run_checked(args: list[str], *, env: dict[str, str] | None = None) -> None:
    print("Running:", " ".join(args[:2] + ["..."] if len(args) > 2 else args), flush=True)
    subprocess.run(args, check=True, env=env)


def main() -> None:
    pg_dump = shutil.which("pg_dump")
    pg_restore = shutil.which("pg_restore")
    if not pg_dump or not pg_restore:
        raise RuntimeError("pg_dump/pg_restore not installed in migration image")

    source = conn_kwargs()
    target = conn_kwargs("NEON_")

    print("Source:", source["host"], source["dbname"], source["user"], flush=True)
    print("Target:", target["host"], target["dbname"], target["user"], flush=True)

    with psycopg.connect(**source) as src:
        source_version = src.execute("SHOW server_version").fetchone()[0]
        source_counts = table_counts(src)
    print(f"Source PostgreSQL: {source_version}; public tables: {len(source_counts)}", flush=True)
    if not source_counts:
        raise RuntimeError("Source public schema has no tables; refusing migration")

    with psycopg.connect(**target) as dst:
        target_version = dst.execute("SHOW server_version").fetchone()[0]
        existing = table_counts(dst)
    print(f"Target PostgreSQL: {target_version}; existing public tables: {len(existing)}", flush=True)
    if existing:
        raise RuntimeError(
            "Target public schema is not empty. Migration runner refuses to overwrite existing tables: "
            + ", ".join(sorted(existing)[:20])
        )

    with tempfile.TemporaryDirectory(prefix="vera-neon-migrate-") as tmp:
        dump_path = Path(tmp) / "vera-public.dump"

        source_env = os.environ.copy()
        source_env["PGPASSWORD"] = source["password"]
        run_checked(
            [
                pg_dump,
                "--format=custom",
                "--schema=public",
                "--no-owner",
                "--no-privileges",
                "--verbose",
                "--host", source["host"],
                "--port", str(source["port"]),
                "--username", source["user"],
                "--dbname", source["dbname"],
                "--file", str(dump_path),
            ],
            env=source_env,
        )

        target_env = os.environ.copy()
        target_env["PGSSLMODE"] = target["sslmode"]
        run_checked(
            [
                pg_restore,
                "--exit-on-error",
                "--no-owner",
                "--no-privileges",
                "--verbose",
                "--host", target["host"],
                "--port", str(target["port"]),
                "--username", target["user"],
                "--dbname", target["dbname"],
                str(dump_path),
            ],
            env=target_env,
        )

    with psycopg.connect(**target) as dst:
        target_counts = table_counts(dst)

    missing_tables = sorted(set(source_counts) - set(target_counts))
    extra_tables = sorted(set(target_counts) - set(source_counts))
    mismatches = {
        table: {"source": source_counts[table], "target": target_counts.get(table)}
        for table in source_counts
        if target_counts.get(table) != source_counts[table]
    }

    report = {
        "source_table_count": len(source_counts),
        "target_table_count": len(target_counts),
        "missing_tables": missing_tables,
        "extra_tables": extra_tables,
        "row_count_mismatches": mismatches,
    }
    print("MIGRATION_VALIDATION=" + json.dumps(report, ensure_ascii=False, sort_keys=True), flush=True)

    if missing_tables or extra_tables or mismatches:
        raise RuntimeError("Migration validation failed; see MIGRATION_VALIDATION above")

    print("MIGRATION_OK: Supabase public schema copied to Neon and row counts match.", flush=True)


if __name__ == "__main__":
    main()
