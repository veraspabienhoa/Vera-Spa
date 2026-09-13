import sqlite3
from concurrent.futures import ThreadPoolExecutor

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import TimeoutError
from sqlalchemy.pool import QueuePool

import vera_web_v2_auth_pool as pools


@pytest.fixture(autouse=True)
def reset_pool(monkeypatch):
    monkeypatch.setattr(pools, '_engine', None)
    monkeypatch.setattr(pools, '_primary', None)
    yield
    if pools._engine is not None:
        pools._engine.dispose()


def test_auth_queries_work_while_business_pool_is_exhausted(tmp_path, monkeypatch):
    path = str(tmp_path / 'auth.db')
    primary = create_engine('sqlite:///' + path, poolclass=QueuePool, pool_size=1, max_overflow=0, pool_timeout=0.01)
    with primary.begin() as conn:
        conn.execute(text('CREATE TABLE sessions (token TEXT, revoked INTEGER)'))
        conn.execute(text("INSERT INTO sessions VALUES ('known', 0)"))
    captured = []
    def factory(url, **kwargs):
        captured.append((url, kwargs))
        kwargs.pop('connect_args')
        return create_engine(url, poolclass=QueuePool, **kwargs)
    monkeypatch.setattr(pools, 'create_engine', factory)
    try:
        with primary.connect():
            with pytest.raises(TimeoutError):
                primary.connect()
            with ThreadPoolExecutor(max_workers=4) as workers:
                engines = list(workers.map(lambda _: pools.auth_engine(primary), range(4)))
            assert all(item is engines[0] for item in engines)
            assert len(captured) == 1
            assert captured[0][0] == primary.url
            assert captured[0][1]['max_overflow'] == 0
            with engines[0].connect() as conn:
                assert conn.execute(text("SELECT count(*) FROM sessions WHERE token='known' AND revoked=0")).scalar_one() == 1
                assert conn.execute(text("SELECT count(*) FROM sessions WHERE token='unknown' AND revoked=0")).scalar_one() == 0
        with primary.begin() as conn:
            conn.execute(text('UPDATE sessions SET revoked=1'))
        with engines[0].connect() as conn:
            assert conn.execute(text("SELECT count(*) FROM sessions WHERE token='known' AND revoked=0")).scalar_one() == 0
    finally:
        primary.dispose()


@pytest.mark.parametrize('sslmode,expected', [('require','require'), ('verify-full','verify-full'), ('disable','require')])
def test_auth_pool_preserves_ssl_and_bounds_capacity(monkeypatch, sslmode, expected):
    from types import SimpleNamespace
    options = {}
    monkeypatch.setenv('DB_SSLMODE', sslmode)
    monkeypatch.setenv('DB_AUTH_POOL_SIZE', '1000')
    monkeypatch.setenv('DB_AUTH_POOL_TIMEOUT', '500')
    monkeypatch.setattr(pools, 'create_engine', lambda url, **kwargs: options.update(kwargs) or SimpleNamespace(dispose=lambda: None))
    pools.auth_engine(SimpleNamespace(url='postgresql+psycopg://unused'))
    assert options['connect_args']['sslmode'] == expected
    assert options['pool_size'] == 4
    assert options['pool_timeout'] == 60
    assert options['max_overflow'] == 0
    assert 'statement_timeout=10000' in options['connect_args']['options']
