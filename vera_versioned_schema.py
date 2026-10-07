"""Transaction-owned, versioned migrations; ordinary reads never repeat DDL.

No process cache: a rollback (including a savepoint) must roll back readiness too.
The small catalog/version reads intentionally use the caller's connection.
"""
from sqlalchemy import text


def _ready(conn, component, version):
    if not conn.execute(text("SELECT to_regclass('vera_read_path_schema')")).scalar():
        return False
    current = conn.execute(text(
        "SELECT version FROM vera_read_path_schema WHERE component=:component"
    ), {"component": component}).scalar()
    return current is not None and int(current) >= version


def ensure(conn, component, version, migrate):
    if _ready(conn, component, version):
        return
    # One global migration lock also serializes creation of the version table.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera.read-path-schema'))"))
    if _ready(conn, component, version):
        return
    conn.execute(text("""CREATE TABLE IF NOT EXISTS vera_read_path_schema (
        component TEXT PRIMARY KEY, version INTEGER NOT NULL,
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
        ALTER TABLE vera_read_path_schema ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON vera_read_path_schema FROM PUBLIC;
        DO $$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON vera_read_path_schema FROM anon; END IF;
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON vera_read_path_schema FROM authenticated; END IF;
        END $$"""))
    migrate(conn)
    conn.execute(text("""INSERT INTO vera_read_path_schema(component,version)
        VALUES(:component,:version) ON CONFLICT(component) DO UPDATE
        SET version=EXCLUDED.version,updated_at=NOW()"""),
        {"component": component, "version": version})


def prepare_read_schemas(conn):
    """Run during the existing deploy schema gate, with its bounded timeouts."""
    from vera_web_v2_work_schedule import _ensure_schema
    from vera_online_booking import ensure_schema
    from vera_web_v2_training import _schema
    from vera_web_v2_staff_security import _ensure_identity_table
    _ensure_schema(conn)
    ensure_schema(conn)
    _schema(conn)
    _ensure_identity_table(conn)
