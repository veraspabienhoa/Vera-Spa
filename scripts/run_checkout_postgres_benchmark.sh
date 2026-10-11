#!/usr/bin/env bash
# Starts a fresh loopback-only PostgreSQL cluster and removes it on exit.
# Requires installed PostgreSQL binaries, Python dependencies and an unprivileged user.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-python}"
PG_BIN="${PG_BIN:-$(dirname "$(command -v initdb || true)")}"
PORT="${VERA_BENCH_PORT:-55443}"
[[ "$PORT" =~ ^[0-9]+$ ]] && (( PORT > 1024 && PORT < 65536 )) || { echo 'Invalid local benchmark port' >&2; exit 2; }
[[ -x "$PG_BIN/initdb" && -x "$PG_BIN/pg_ctl" ]] || { echo 'Set PG_BIN to the installed PostgreSQL bin directory' >&2; exit 2; }
TEMP="$(mktemp -d /tmp/vera-checkout-bench.XXXXXXXX)"
cleanup() {
  "$PG_BIN/pg_ctl" -D "$TEMP/data" -m fast -w stop >/dev/null 2>&1 || true
  rm -rf -- "$TEMP"
}
trap cleanup EXIT
"$PG_BIN/initdb" -D "$TEMP/data" -U postgres -A trust >"$TEMP/initdb.log"
"$PG_BIN/pg_ctl" -D "$TEMP/data" -l "$TEMP/postgres.log" -o "-h 127.0.0.1 -p $PORT -k ''" -w start
export VERA_BENCH_POSTGRES_URL="postgresql+psycopg://postgres@127.0.0.1:$PORT/postgres"
# Keep a caller-supplied offline sitecustomize at the start of PYTHONPATH.
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$ROOT"
cd "$ROOT"
"$PYTHON" scripts/benchmark_checkout_postgres.py "$@"
