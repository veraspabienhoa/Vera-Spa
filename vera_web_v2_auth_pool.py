"""Reserve bounded PostgreSQL connections for login and session verification."""
import os
import threading

from sqlalchemy import create_engine

_lock = threading.Lock()
_primary = None
_engine = None


def auth_engine(primary):
    """Use the same database/SSL policy with a separate, small connection pool.

    Reporting and background jobs must not consume the connections needed to
    validate sessions. No identity is cached: revocation and account locks are
    still checked against PostgreSQL for every authenticated request.
    """
    global _primary, _engine
    with _lock:
        if _engine is not None and _primary is primary:
            return _engine
        sslmode = os.getenv('DB_SSLMODE', 'require').strip().lower() or 'require'
        if sslmode not in {'require', 'verify-ca', 'verify-full'}:
            sslmode = 'require'
        from vera_database_runtime import pool_configuration, validate_runtime_configuration
        validate_runtime_configuration(required_pool='auth')
        configuration = pool_configuration('auth')
        engine = create_engine(
            primary.url,
            **configuration.engine_kwargs(),
            connect_args={**configuration.connect_args(), 'sslmode': sslmode},
        )
        old = _engine
        _primary, _engine = primary, engine
        if old is not None:
            old.dispose()
        return engine
