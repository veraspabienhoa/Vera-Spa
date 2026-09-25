"""Notification reads must not take DDL locks inside business transactions."""
import os
from types import SimpleNamespace
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

import vera_web_v2_notification_settings as settings


class Connection:
    def __init__(self, ready):
        self.ready = iter(ready)
        self.statements = []

    def execute(self, sql):
        sql = str(sql)
        self.statements.append(sql)
        value = next(self.ready) if 'SELECT to_regclass' in sql else None
        return SimpleNamespace(scalar_one_or_none=lambda: value)


def test_ready_schema_does_not_acquire_ddl_or_advisory_locks():
    conn = Connection([True])
    settings.ensure_schema(conn)
    assert len(conn.statements) == 1
    assert conn.statements[0].lstrip().startswith('SELECT')


def test_schema_is_rechecked_after_serializing_initialization():
    conn = Connection([False, True])
    settings.ensure_schema(conn)
    assert len(conn.statements) == 3
    assert 'pg_advisory_xact_lock' in conn.statements[1]
    assert not any(sql.lstrip().startswith(('CREATE', 'ALTER', 'REVOKE', 'DO')) for sql in conn.statements)


@pytest.fixture
def database():
    value = os.getenv('VERA_TEST_POSTGRES_URL')
    if not value:
        pytest.skip('isolated PostgreSQL integration service is not configured')
    url = make_url(value)
    if url.database != 'vera_test':
        pytest.fail('schema lock tests require the isolated vera_test database')
    name = 'notification_lock_test_' + uuid4().hex
    owner = create_engine(url, isolation_level='AUTOCOMMIT')
    with owner.connect() as conn:
        conn.exec_driver_sql(f'CREATE DATABASE "{name}"')
    engine = create_engine(url.set(database=name))
    try:
        yield engine
    finally:
        engine.dispose()
        with owner.connect() as conn:
            conn.exec_driver_sql(f'DROP DATABASE "{name}" WITH (FORCE)')
        owner.dispose()


def test_existing_switch_read_does_not_block_other_transactions(database):
    with database.begin() as conn:
        settings.ensure_schema(conn)
        conn.execute(text("INSERT INTO vera_v2_notification_setting(notification_key,enabled) VALUES ('birthday',FALSE)"))
    with database.begin() as business:
        assert settings.is_enabled(business, 'birthday') is False
        with database.begin() as other:
            other.execute(text("SET LOCAL lock_timeout='500ms'"))
            assert settings.is_enabled(other, 'birthday') is False
            other.execute(text("INSERT INTO vera_v2_notification_channel_setting(notification_key,channel,enabled,updated_by) VALUES ('birthday','popup',FALSE,'test')"))


def test_migration_preserves_switches_and_restores_security(database):
    with database.begin() as conn:
        settings.ensure_schema(conn)
        conn.execute(text("INSERT INTO vera_v2_notification_channel_setting(notification_key,channel,enabled,updated_by) VALUES ('birthday','push',FALSE,'test')"))
        conn.execute(text("ALTER TABLE vera_v2_notification_channel_setting DROP CONSTRAINT vera_v2_notification_channel_setting_channel_check"))
        conn.execute(text("ALTER TABLE vera_v2_notification_channel_setting ADD CONSTRAINT vera_v2_notification_channel_setting_channel_check CHECK(channel IN ('in_app','push'))"))
        conn.execute(text('ALTER TABLE vera_v2_notification_channel_setting DISABLE ROW LEVEL SECURITY'))
        conn.execute(text('GRANT SELECT ON vera_v2_notification_channel_setting TO PUBLIC'))
    with database.begin() as conn:
        assert settings._schema_ready(conn) is False
        settings.ensure_schema(conn)
        assert settings._schema_ready(conn) is True
        assert settings.is_channel_enabled(conn, 'birthday', 'push') is False
        conn.execute(text("INSERT INTO vera_v2_notification_channel_setting(notification_key,channel,enabled,updated_by) VALUES ('birthday','popup',FALSE,'test')"))


def test_rolled_back_initialization_is_not_cached(database):
    with database.connect() as conn:
        settings.ensure_schema(conn)
        conn.rollback()
    with database.begin() as conn:
        assert settings._schema_ready(conn) is False
        settings.ensure_schema(conn)
        assert settings._schema_ready(conn) is True
