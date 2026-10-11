"""Bounded connection settings and process-local, data-free pool observations.

Capacity bounds are configuration guardrails, not a statement of host capacity.
A fleet budget is trusted only when the operator explicitly declares every pool
instance and all other connection reservations. No OS/database settings change.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
from threading import Lock
from time import monotonic
from typing import Mapping

from sqlalchemy.exc import TimeoutError as PoolTimeout
from sqlalchemy.pool import QueuePool


BUDGET_KEYS = frozenset({
    'DB_CONNECTION_BUDGET', 'DB_API_POOL_INSTANCES', 'DB_BACKGROUND_POOL_INSTANCES',
    'DB_DEDICATED_CONNECTIONS', 'DB_EXTERNAL_CONNECTION_RESERVE',
})
POOL_ENV_KEYS = BUDGET_KEYS | frozenset({
    'DB_POOL_SIZE', 'DB_MAX_OVERFLOW', 'DB_POOL_TIMEOUT', 'DB_POOL_RECYCLE',
    'DB_CONNECT_TIMEOUT', 'DB_BACKGROUND_POOL_SIZE', 'DB_BACKGROUND_MAX_OVERFLOW',
    'DB_AUTH_POOL_SIZE', 'DB_AUTH_POOL_TIMEOUT', 'DB_STATEMENT_TIMEOUT_MS',
    'DB_LOCK_TIMEOUT_MS', 'DB_IDLE_IN_TRANSACTION_TIMEOUT_MS',
})
_DEADLINES = {
    'DB_STATEMENT_TIMEOUT_MS': ('statement_timeout', 900_000),
    'DB_LOCK_TIMEOUT_MS': ('lock_timeout', 60_000),
    'DB_IDLE_IN_TRANSACTION_TIMEOUT_MS': ('idle_in_transaction_session_timeout', 900_000),
}
_BUCKETS_MS = (1, 5, 10, 50, 100, 500, 1000, 5000, 30000)
_LOGGER = logging.getLogger('uvicorn.error')


def _integer(env, key, default, minimum, maximum, *, clamp=False):
    raw = env.get(key, default)
    try:
        value = int(str(raw).strip())
    except (TypeError, ValueError):
        # Do not echo user configuration: an accidentally pasted value may be a secret.
        raise ValueError(f'{key} must be an integer') from None
    if clamp:
        return max(minimum, min(maximum, value))
    if not minimum <= value <= maximum:
        raise ValueError(f'{key} is outside the supported range {minimum}..{maximum}')
    return value


@dataclass(frozen=True)
class PoolConfiguration:
    role: str
    size: int
    overflow: int
    timeout: int
    recycle: int
    connect_timeout: int
    options: str

    @property
    def capacity(self):
        return self.size + self.overflow

    def engine_kwargs(self):
        return {
            'poolclass': ObservedQueuePool, 'pool_size': self.size,
            'max_overflow': self.overflow, 'pool_timeout': self.timeout,
            'pool_recycle': self.recycle, 'pool_pre_ping': True,
            'pool_logging_name': self.role,
        }

    def connect_args(self):
        values = {'connect_timeout': self.connect_timeout}
        if self.options:
            values['options'] = self.options
        values['application_name'] = {
            'api_business': 'vera-web-v2-business',
            'background': 'vera-background', 'auth': 'vera-web-v2-auth',
        }[self.role]
        return values


def pool_configuration(role='api', env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    if role not in {'api', 'background', 'auth'}:
        raise ValueError('Unknown database pool role')
    size = _integer(env, 'DB_POOL_SIZE', 2, 1, 64)
    overflow = _integer(env, 'DB_MAX_OVERFLOW', 0, 0, 64)
    timeout = _integer(env, 'DB_POOL_TIMEOUT', 30 if role == 'api' else 20, 1, 120)
    recycle = _integer(env, 'DB_POOL_RECYCLE', 3600, 3600, 86400)
    connect_timeout = _integer(env, 'DB_CONNECT_TIMEOUT', 10, 3, 120)
    options = []
    deadlines = {}
    for key, (setting, maximum) in _DEADLINES.items():
        if key in env:
            deadlines[setting] = _integer(env, key, None, 1, maximum)
            options.append(f'-c {setting}={deadlines[setting]}')
    if deadlines.get('lock_timeout', 0) > deadlines.get('statement_timeout', 900_000):
        raise ValueError('DB_LOCK_TIMEOUT_MS must not exceed DB_STATEMENT_TIMEOUT_MS')
    if role == 'background':
        size = _integer(env, 'DB_BACKGROUND_POOL_SIZE', env.get('DB_POOL_SIZE', 8), 1, 64)
        overflow = _integer(env, 'DB_BACKGROUND_MAX_OVERFLOW', env.get('DB_MAX_OVERFLOW', 12), 0, 64)
    elif role == 'auth':
        # Preserve the existing auth clamps and fixed, bounded SQL deadlines.
        size = _integer(env, 'DB_AUTH_POOL_SIZE', 2, 1, 4, clamp=True)
        overflow = 0
        timeout = _integer(env, 'DB_AUTH_POOL_TIMEOUT', 5, 1, 60, clamp=True)
        options = ['-c statement_timeout=10000 -c lock_timeout=3000 '
                   '-c idle_in_transaction_session_timeout=15000']
    return PoolConfiguration('api_business' if role == 'api' else role, size, overflow,
                             timeout, recycle, connect_timeout, ' '.join(options))


def connection_budget(env: Mapping[str, str] | None = None):
    env = os.environ if env is None else env
    api = pool_configuration('api', env)
    auth = pool_configuration('auth', env)
    background = pool_configuration('background', env)
    result = {
        'status': 'undeclared', 'api_pair_capacity': api.capacity + auth.capacity,
        'background_capacity': background.capacity,
    }
    present = BUDGET_KEYS & env.keys()
    if not present:
        return result
    if present != BUDGET_KEYS:
        raise ValueError('Database connection budget requires all five budget settings')
    api_instances = _integer(env, 'DB_API_POOL_INSTANCES', None, 0, 1024)
    background_instances = _integer(env, 'DB_BACKGROUND_POOL_INSTANCES', None, 0, 1024)
    dedicated = _integer(env, 'DB_DEDICATED_CONNECTIONS', None, 0, 100_000)
    reserve = _integer(env, 'DB_EXTERNAL_CONNECTION_RESERVE', None, 0, 100_000)
    budget = _integer(env, 'DB_CONNECTION_BUDGET', None, 1, 100_000)
    required = api_instances * (api.capacity + auth.capacity) + background_instances * background.capacity + dedicated + reserve
    if api_instances + background_instances < 1:
        raise ValueError('Database connection budget must include an application pool instance')
    if required > budget:
        raise ValueError('Declared database connection demand exceeds DB_CONNECTION_BUDGET')
    return {**result, 'status': 'within_declared_budget', 'api_pool_instances': api_instances,
            'background_pool_instances': background_instances, 'dedicated_connections': dedicated,
            'external_reserve': reserve, 'budget': budget, 'required': required,
            'headroom': budget - required}


def validate_runtime_configuration(env: Mapping[str, str] | None = None, *, required_pool=None):
    """Validate before opening pools; no I/O, host inference, or server changes."""
    env = os.environ if env is None else env
    if env.get('VERA_SERVICE_ROLE', 'combined') not in {'combined', 'api', 'worker'}:
        raise ValueError('VERA_SERVICE_ROLE must be combined, api or worker')
    budget = connection_budget(env)
    if required_pool not in {None, 'api', 'auth', 'background'}:
        raise ValueError('Unknown required database pool role')
    if budget['status'] != 'undeclared' and required_pool is not None:
        count_key = 'background_pool_instances' if required_pool == 'background' else 'api_pool_instances'
        if budget[count_key] < 1:
            raise ValueError('Declared database budget omits the requested pool type')
    return budget


class ObservedQueuePool(QueuePool):
    """Observe public pool acquisition, including connect/pre-ping, without payloads.

    Counters reset on engine disposal/pool recreation. Waiting includes connection
    establishment and pre-ping; it is not exclusively queue time or query time.
    No record identifiers, URL, SQL, exception strings or thread IDs are retained.
    """

    def __init__(self, *args, **kwargs):
        self._observation_lock = Lock()
        self._acquiring = 0
        self._acquired = 0
        self._timeouts = 0
        self._errors = 0
        self._acquire_ms = 0.0
        self._max_acquire_ms = 0.0
        self._acquire_buckets = [0] * (len(_BUCKETS_MS) + 1)
        self._last_observation_log = monotonic()
        super().__init__(*args, **kwargs)

    def connect(self):
        started = monotonic()
        outcome = 'ok'
        with self._observation_lock:
            self._acquiring += 1
        try:
            return super().connect()
        except PoolTimeout:
            outcome = 'timeout'
            raise
        except Exception:
            outcome = 'error'
            raise
        finally:
            elapsed = (monotonic() - started) * 1000
            with self._observation_lock:
                self._acquiring -= 1
                self._acquired += outcome == 'ok'
                self._timeouts += outcome == 'timeout'
                self._errors += outcome == 'error'
                self._acquire_ms += elapsed
                self._max_acquire_ms = max(self._max_acquire_ms, elapsed)
                index = next((i for i, limit in enumerate(_BUCKETS_MS) if elapsed <= limit), len(_BUCKETS_MS))
                self._acquire_buckets[index] += 1
                emit = monotonic() - self._last_observation_log >= 60
                if emit:
                    self._last_observation_log = monotonic()
            if emit:
                _LOGGER.info('VERA_POOL_METRICS %s', json.dumps(self.observation(), separators=(',', ':')))

    def observation(self):
        with self._observation_lock:
            role = self._orig_logging_name
            if role not in {'api_business', 'background', 'auth'}:
                role = 'other'
            return {
                'pool': role, 'size': self.size(), 'overflow_limit': self._max_overflow,
                'checked_in': self.checkedin(), 'checked_out': self.checkedout(),
                'overflow': max(0, self.overflow()), 'acquiring': self._acquiring,
                'acquired': self._acquired, 'timeouts': self._timeouts, 'errors': self._errors,
                'acquire_ms': round(self._acquire_ms, 2),
                'max_acquire_ms': round(self._max_acquire_ms, 2),
                'acquire_buckets': list(self._acquire_buckets),
            }


def pool_observation(engine):
    pool = getattr(engine, 'pool', None)
    return pool.observation() if isinstance(pool, ObservedQueuePool) else {'pool': 'unobserved'}


def connection_deadlines(conn):
    """Read numeric effective deadlines from this connection, including role policy."""
    from sqlalchemy import text
    rows = conn.execute(text("""
        SELECT name, setting::bigint AS milliseconds FROM pg_settings
        WHERE name IN ('statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout')
        ORDER BY name
    """)).mappings().all()
    allowed = {'statement_timeout', 'lock_timeout', 'idle_in_transaction_session_timeout'}
    return {row['name']: int(row['milliseconds']) for row in rows if row['name'] in allowed}
