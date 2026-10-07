"""Transactional change tokens for every writer of revenue source tables."""
from sqlalchemy import text

SOURCES = ('vera_live_tour_report', 'vera_purchase_entry', 'vera_revenue_entry', 'vera_app_setting')


def install(conn):
    from vera_versioned_schema import ensure
    ensure(conn, 'revenue_revision', 1, _migrate)


def _migrate(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS vera_revenue_change_version (
        source TEXT PRIMARY KEY, revision BIGINT NOT NULL DEFAULT 0);
        ALTER TABLE vera_revenue_change_version ENABLE ROW LEVEL SECURITY;
        REVOKE ALL ON vera_revenue_change_version FROM PUBLIC;
        DO $$ BEGIN
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='anon') THEN REVOKE ALL ON vera_revenue_change_version FROM anon; END IF;
          IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN REVOKE ALL ON vera_revenue_change_version FROM authenticated; END IF;
        END $$;
        CREATE OR REPLACE FUNCTION vera_bump_revenue_revision() RETURNS trigger
        LANGUAGE plpgsql AS $$ BEGIN
            IF TG_TABLE_NAME = 'vera_app_setting' THEN
                IF TG_OP = 'INSERT' AND NEW.category <> 'revenue' THEN RETURN NULL; END IF;
                IF TG_OP = 'DELETE' AND OLD.category <> 'revenue' THEN RETURN NULL; END IF;
                IF TG_OP = 'UPDATE' AND OLD.category <> 'revenue' AND NEW.category <> 'revenue' THEN RETURN NULL; END IF;
            END IF;
            UPDATE vera_revenue_change_version SET revision=revision+1 WHERE source=TG_TABLE_NAME;
            RETURN NULL;
        END $$"""))
    for table in SOURCES:
        # Server-owned identifiers only. Triggers include imports, adjustments,
        # soft/hard deletion and alternate writers, in the source transaction.
        conn.execute(text("INSERT INTO vera_revenue_change_version(source) VALUES(:source) ON CONFLICT DO NOTHING"), {'source': table})
        conn.execute(text(f'DROP TRIGGER IF EXISTS vera_revenue_change ON {table}'))
        level = 'ROW' if table == 'vera_app_setting' else 'STATEMENT'
        conn.execute(text(f'''CREATE TRIGGER vera_revenue_change AFTER INSERT OR UPDATE OR DELETE ON {table}
            FOR EACH {level} EXECUTE FUNCTION vera_bump_revenue_revision()'''))
        if table != 'vera_app_setting':
            conn.execute(text(f'DROP TRIGGER IF EXISTS vera_revenue_truncate ON {table}'))
            conn.execute(text(f'''CREATE TRIGGER vera_revenue_truncate AFTER TRUNCATE ON {table}
                FOR EACH STATEMENT EXECUTE FUNCTION vera_bump_revenue_revision()'''))


def read(conn):
    # Old releases/databases remain readable until the deploy gate installs all
    # triggers atomically. Never install DDL or cache a token on a poll request.
    if not conn.execute(text("SELECT to_regclass('vera_revenue_change_version')")).scalar():
        return None
    rows = conn.execute(text("SELECT source,revision FROM vera_revenue_change_version ORDER BY source")).mappings().all()
    if {row['source'] for row in rows} != set(SOURCES):
        return None
    return [(row['source'], int(row['revision'])) for row in rows]
