"""Configuration, saturation, sanitization and isolated PostgreSQL regressions."""
from concurrent.futures import ThreadPoolExecutor
import json
import os
import time
from types import SimpleNamespace

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import DBAPIError, TimeoutError

import vera_database_runtime as runtime


def declared(**changes):
    return {
        'DB_CONNECTION_BUDGET': '100', 'DB_API_POOL_INSTANCES': '3',
        'DB_BACKGROUND_POOL_INSTANCES': '2', 'DB_DEDICATED_CONNECTIONS': '1',
        'DB_EXTERNAL_CONNECTION_RESERVE': '10', **changes,
    }


def test_defaults_preserve_existing_separate_capacities_and_deadlines():
    api = runtime.pool_configuration('api', {})
    auth = runtime.pool_configuration('auth', {})
    background = runtime.pool_configuration('background', {})
    assert (api.size, api.overflow, api.timeout) == (2, 0, 30)
    assert (auth.size, auth.overflow, auth.timeout) == (2, 0, 5)
    assert (background.size, background.overflow, background.timeout) == (8, 12, 20)
    assert not api.options and not background.options  # retain database/role policies
    assert auth.options == '-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=15000'
    assert runtime.connection_budget({})['status'] == 'undeclared'


def test_explicit_fleet_budget_counts_both_pools_background_and_reservations():
    budget = runtime.validate_runtime_configuration(declared())
    assert budget['required'] == 3 * (2 + 2) + 2 * (8 + 12) + 1 + 10 == 63
    assert budget['headroom'] == 37
    assert budget['status'] == 'within_declared_budget'
    assert runtime.connection_budget(declared(DB_CONNECTION_BUDGET='63'))['headroom'] == 0
    with pytest.raises(ValueError, match='demand exceeds'):
        runtime.connection_budget(declared(DB_CONNECTION_BUDGET='62'))


@pytest.mark.parametrize('key', runtime.BUDGET_KEYS)
def test_partial_budget_is_rejected(key):
    env = declared()
    del env[key]
    with pytest.raises(ValueError, match='all five'):
        runtime.validate_runtime_configuration(env)


@pytest.mark.parametrize('env', [
    {'DB_POOL_SIZE': '0'}, {'DB_MAX_OVERFLOW': '-1'}, {'DB_POOL_SIZE': '65'},
    {'DB_MAX_OVERFLOW': '65'}, {'DB_CONNECT_TIMEOUT': '121'}, {'DB_POOL_TIMEOUT': '0'},
    {'DB_POOL_RECYCLE': '99999999'}, {'DB_STATEMENT_TIMEOUT_MS': '0'},
    {'DB_LOCK_TIMEOUT_MS': '60001'}, {'DB_IDLE_IN_TRANSACTION_TIMEOUT_MS': '-1'},
    {'DB_LOCK_TIMEOUT_MS': '200', 'DB_STATEMENT_TIMEOUT_MS': '100'},
    {'VERA_SERVICE_ROLE': 'api worker'}, {'DB_BACKGROUND_POOL_SIZE': '0'},
    declared(DB_API_POOL_INSTANCES='0', DB_BACKGROUND_POOL_INSTANCES='0'),
])
def test_invalid_or_unbounded_configuration_fails_closed(env):
    with pytest.raises(ValueError):
        runtime.validate_runtime_configuration(env)


def test_bad_values_never_appear_in_validation_errors():
    with pytest.raises(ValueError) as error:
        runtime.validate_runtime_configuration({'DB_POOL_TIMEOUT': 'postgresql://private-user:private-password@private-host'})
    assert 'private' not in str(error.value)


def test_background_overrides_keep_legacy_fallback_and_change_budget():
    common = {'DB_POOL_SIZE': '5', 'DB_MAX_OVERFLOW': '3'}
    assert runtime.pool_configuration('background', common).capacity == 8
    explicit = {**common, 'DB_BACKGROUND_POOL_SIZE': '1', 'DB_BACKGROUND_MAX_OVERFLOW': '0'}
    assert runtime.pool_configuration('api', explicit).capacity == 8
    assert runtime.pool_configuration('background', explicit).capacity == 1
    assert runtime.connection_budget({**declared(), **explicit})['required'] == 3 * (8 + 2) + 2 + 1 + 10


def test_auth_clamps_still_hold_and_ignore_business_sql_deadline_override():
    config = runtime.pool_configuration('auth', {
        'DB_AUTH_POOL_SIZE': '999', 'DB_AUTH_POOL_TIMEOUT': '999', 'DB_STATEMENT_TIMEOUT_MS': '100',
    })
    assert (config.size, config.overflow, config.timeout) == (4, 0, 60)
    assert 'statement_timeout=10000' in config.options


def test_observations_count_saturation_errors_and_pool_recreation_without_payloads(tmp_path):
    engine = create_engine('sqlite:///' + str(tmp_path / 'private-database.db'),
                           poolclass=runtime.ObservedQueuePool, pool_size=1,
                           max_overflow=0, pool_timeout=0.03, pool_logging_name='auth')
    try:
        with engine.connect():
            with pytest.raises(TimeoutError):
                engine.connect()
            state = runtime.pool_observation(engine)
            assert state['checked_out'] == 1
            assert state['timeouts'] == 1
            assert state['acquired'] == 1
            assert sum(state['acquire_buckets']) == 2
            assert state['max_acquire_ms'] >= 20
        state = runtime.pool_observation(engine)
        assert state['checked_out'] == 0 and state['checked_in'] == 1
        assert 'private' not in json.dumps(state)
        engine.dispose()
        with engine.connect():
            pass
        assert runtime.pool_observation(engine)['acquired'] == 1
        assert runtime.pool_observation(engine)['timeouts'] == 0
    finally:
        engine.dispose()


def test_connection_failure_observation_does_not_retain_error():
    def fail():
        raise RuntimeError('private-password private-token')
    pool = runtime.ObservedQueuePool(fail, pool_size=1, max_overflow=0,
                                     logging_name='private-name')
    with pytest.raises(RuntimeError):
        pool.connect()
    state = pool.observation()
    assert state['errors'] == 1 and state['acquiring'] == 0
    assert 'private' not in json.dumps(state)
    assert state['pool'] == 'other'


def test_pool_metric_logs_allow_only_fixed_numeric_fields():
    from vera_vps_runtime_diagnostics import safe_log_summary
    metrics = {'pool': 'auth', 'size': 2, 'timeouts': 3, 'acquire_ms': 4.125,
               'errors': 'private', 'token': 'private-token', 'url': 'postgresql://private'}
    assert safe_log_summary('VERA_POOL_METRICS ' + json.dumps(metrics)) == [
        'pool_metrics pool=auth size=2 timeouts=3 acquire_ms=4.12']
    assert safe_log_summary('VERA_POOL_METRICS ' + json.dumps({**metrics, 'pool': 'private'})) == []


def test_effective_managed_config_is_validated_before_mutation(monkeypatch):
    import vera_web_v2_runtime_env as managed
    values = dict(VERA_DB_ENABLED='1', VERA_DATA_BACKEND='postgres', DB_HOST='db.invalid',
                  DB_PORT='5432', DB_NAME='vera', DB_USER='user', DB_PASS='test-only',
                  DB_SSLMODE='require', DB_CONNECT_TIMEOUT='10', VERA_AUTH_PROVIDER='local')
    monkeypatch.setattr(managed, '_read_private_file', lambda path: '\n'.join(f'{k}={v}' for k, v in values.items()))
    monkeypatch.setenv('DB_POOL_SIZE', '0')
    monkeypatch.setenv('DB_HOST', 'unchanged')
    with pytest.raises(RuntimeError, match='invalid'):
        managed.load_managed_runtime_environment()
    assert os.environ['DB_HOST'] == 'unchanged'


def test_api_pool_initialization_is_singleton_under_concurrent_first_use(monkeypatch):
    import vera_web_v2_api as api
    monkeypatch.setattr(api, '_engine', None)
    monkeypatch.setenv('DB_HOST', 'db.invalid')
    monkeypatch.setenv('DB_USER', 'synthetic')
    monkeypatch.setenv('DB_PASS', 'synthetic')
    calls = []
    def factory(url, **kwargs):
        calls.append(kwargs)
        time.sleep(0.02)
        return SimpleNamespace()
    monkeypatch.setattr(api, 'create_engine', factory)
    with ThreadPoolExecutor(max_workers=8) as workers:
        engines = list(workers.map(lambda _: api._engine_instance(), range(8)))
    assert len(calls) == 1 and all(item is engines[0] for item in engines)
    assert calls[0]['pool_timeout'] == 30
    assert calls[0]['connect_args']['sslmode'] == 'require'


def test_business_health_failure_is_retryable_and_sanitized(monkeypatch):
    import vera_web_v2_api as api
    def fail():
        raise RuntimeError('private-token PostgreSQL private-host')
    monkeypatch.setattr(api, '_engine_instance', fail)
    with pytest.raises(api.HTTPException) as error:
        api.health()
    assert error.value.status_code == 503
    assert error.value.detail == 'Business database is unavailable'


@pytest.fixture
def postgres_url():
    url = os.getenv('VERA_TEST_POSTGRES_URL')
    if not url:
        pytest.skip('isolated VERA_TEST_POSTGRES_URL required')
    return url


def test_postgres_deadlines_cancel_waits_and_allow_rollback_reuse(postgres_url):
    config = runtime.pool_configuration('api', {'DB_POOL_SIZE': '2', 'DB_STATEMENT_TIMEOUT_MS': '100',
                                               'DB_LOCK_TIMEOUT_MS': '40', 'DB_IDLE_IN_TRANSACTION_TIMEOUT_MS': '1000'})
    engine = create_engine(postgres_url, **config.engine_kwargs(), connect_args=config.connect_args())
    try:
        with engine.connect() as conn:
            assert runtime.connection_deadlines(conn) == {
                'statement_timeout': 100, 'lock_timeout': 40, 'idle_in_transaction_session_timeout': 1000}
            assert conn.execute(text("SELECT current_setting('statement_timeout')")).scalar_one() == '100ms'
            conn.rollback()
            with pytest.raises(DBAPIError) as error:
                conn.execute(text('SELECT pg_sleep(1)'))
            assert error.value.orig.sqlstate == '57014'
            conn.rollback()
            assert conn.execute(text('SELECT 1')).scalar_one() == 1
        with engine.begin() as holder:
            holder.execute(text('SELECT pg_advisory_xact_lock(891124001)'))
            with engine.connect() as waiter:
                with pytest.raises(DBAPIError) as error:
                    waiter.execute(text('SELECT pg_advisory_xact_lock(891124001)'))
                assert error.value.orig.sqlstate == '55P03'
                waiter.rollback()
                assert waiter.execute(text('SELECT 1')).scalar_one() == 1
        assert runtime.pool_observation(engine)['checked_out'] == 0
    finally:
        engine.dispose()


def test_postgres_auth_reserve_stays_available_when_business_pool_is_full(postgres_url, monkeypatch):
    import vera_web_v2_auth_pool as auth
    monkeypatch.setattr(auth, '_engine', None)
    monkeypatch.setattr(auth, '_primary', None)
    monkeypatch.setenv('DB_POOL_SIZE', '1')
    monkeypatch.setenv('DB_MAX_OVERFLOW', '0')
    monkeypatch.setenv('DB_AUTH_POOL_SIZE', '1')
    config = runtime.pool_configuration('api')
    kwargs = {**config.engine_kwargs(), 'pool_timeout': 0.03}
    business = create_engine(postgres_url, **kwargs, connect_args=config.connect_args())
    def local_factory(url, **kwargs):
        kwargs['connect_args'].pop('sslmode')  # local isolated test server only
        return create_engine(url, **kwargs)
    monkeypatch.setattr(auth, 'create_engine', local_factory)
    try:
        with business.connect():
            with pytest.raises(TimeoutError):
                business.connect()
            with auth.auth_engine(business).connect() as conn:
                assert conn.execute(text('SELECT 1')).scalar_one() == 1
                assert conn.execute(text("SELECT current_setting('statement_timeout')")).scalar_one() == '10s'
                assert conn.execute(text("SELECT current_setting('lock_timeout')")).scalar_one() == '3s'
        assert runtime.pool_observation(business)['timeouts'] == 1
        assert runtime.pool_observation(auth._engine)['acquired'] == 1
    finally:
        business.dispose()
        if auth._engine is not None:
            auth._engine.dispose()


def test_postgres_capacity_diagnostics_are_numeric_or_allowlisted(postgres_url):
    from vera_vps_runtime_diagnostics import CAPACITY_SQL, ROLE_DEADLINE_SQL
    engine = create_engine(postgres_url)
    try:
        with engine.connect() as conn:
            capacity = dict(conn.execute(text(CAPACITY_SQL)).mappings().one())
            deadlines = conn.execute(text(ROLE_DEADLINE_SQL)).mappings().all()
            assert all(type(value) is int for value in capacity.values())
            assert capacity['max_connections'] > 0
            for item in deadlines:
                assert item['source'] in {'role', 'database', 'database_role'}
                assert item['setting'] in {'statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout'}
    finally:
        engine.dispose()


@pytest.mark.parametrize('role', ['combined', 'api', 'worker', 'invalid-role'])
def test_process_role_takes_precedence_over_shared_managed_file(monkeypatch, role):
    import vera_web_v2_runtime_env as managed
    values = dict(VERA_DB_ENABLED='1', VERA_DATA_BACKEND='postgres', DB_HOST='db.invalid',
                  DB_PORT='5432', DB_NAME='vera', DB_USER='user', DB_PASS='test-only',
                  DB_SSLMODE='require', DB_CONNECT_TIMEOUT='10', VERA_AUTH_PROVIDER='local',
                  VERA_SERVICE_ROLE='combined')
    monkeypatch.setattr(managed, '_read_private_file', lambda path: '\n'.join(f'{k}={v}' for k, v in values.items()))
    for key in values:
        monkeypatch.setenv(key, os.environ.get(key, ''))
    monkeypatch.setenv('VERA_SERVICE_ROLE', role)
    if role == 'invalid-role':
        with pytest.raises(RuntimeError, match='invalid'):
            managed.load_managed_runtime_environment()
    else:
        assert managed.load_managed_runtime_environment()
    assert os.environ['VERA_SERVICE_ROLE'] == role


def test_background_pool_first_use_is_serialized_and_failed_creation_disposes(monkeypatch):
    import vera_postgres as postgres
    postgres._cached_engine.cache_clear()
    monkeypatch.setattr(postgres, 'is_enabled', lambda: True)
    calls = []
    disposed = []
    def factory(*args, **kwargs):
        calls.append(kwargs)
        time.sleep(0.02)
        return SimpleNamespace(dispose=lambda: disposed.append(True))
    monkeypatch.setattr(postgres, 'create_engine', factory)
    monkeypatch.setattr(postgres, 'ensure_schema', lambda engine: None)
    try:
        with ThreadPoolExecutor(max_workers=8) as workers:
            engines = list(workers.map(lambda _: postgres.get_engine(), range(8)))
        assert len(calls) == 1 and all(item is engines[0] for item in engines)
        assert (calls[0]['pool_size'], calls[0]['max_overflow']) == (8, 12)
        postgres._cached_engine.cache_clear()
        def fail(engine):
            raise RuntimeError('synthetic')
        monkeypatch.setattr(postgres, 'ensure_schema', fail)
        with pytest.raises(RuntimeError):
            postgres.get_engine()
        assert len(disposed) == 1
    finally:
        postgres._cached_engine.cache_clear()


@pytest.mark.parametrize('role,env', [
    ('api', declared(DB_API_POOL_INSTANCES='0')),
    ('auth', declared(DB_API_POOL_INSTANCES='0')),
    ('background', declared(DB_BACKGROUND_POOL_INSTANCES='0')),
])
def test_engine_creation_cannot_use_an_omitted_pool_type(role, env):
    with pytest.raises(ValueError, match='omits the requested pool'):
        runtime.validate_runtime_configuration(env, required_pool=role)


def test_postgres_health_retains_storage_check_and_reports_actual_deadlines(postgres_url, monkeypatch):
    import vera_web_v2_api as api
    import vera_live_tour_relational as storage
    config = runtime.pool_configuration('api', {'DB_STATEMENT_TIMEOUT_MS': '500', 'DB_LOCK_TIMEOUT_MS': '100'})
    engine = create_engine(postgres_url, **config.engine_kwargs(), connect_args=config.connect_args())
    monkeypatch.setattr(api, '_engine_instance', lambda: engine)
    monkeypatch.setattr(storage, 'resource_ready', lambda conn: False)
    monkeypatch.setattr(storage, 'mode', lambda: 'shadow')
    try:
        result = api.health()
        assert result['ok'] is True
        assert result['live_tour_storage_ready'] is False
        assert result['database_pool']['checked_out'] == 0
        assert result['database_deadlines_ms']['statement_timeout'] == 500
        assert result['database_deadlines_ms']['lock_timeout'] == 100
        assert result['database_budget']['status'] == 'undeclared'
        assert 'postgresql' not in json.dumps(result)
        monkeypatch.setattr(storage, 'mode', lambda: 'active')
        with pytest.raises(api.HTTPException) as error:
            api.health()
        assert error.value.status_code == 503
    finally:
        engine.dispose()
