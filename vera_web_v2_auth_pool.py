"""Reserve bounded PostgreSQL connections for login and session verification."""
import os
import threading

from sqlalchemy import create_engine

_lock = threading.Lock()
_primary = None
_engine = None


def _seconds(name, default):
    return max(1, min(60, int(os.getenv(name, str(default)))))


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
        engine = create_engine(
            primary.url,
            pool_size=max(1, min(4, int(os.getenv('DB_AUTH_POOL_SIZE', '2')))),
            max_overflow=0,
            pool_timeout=_seconds('DB_AUTH_POOL_TIMEOUT', 5),
            pool_pre_ping=True,
            pool_recycle=max(3600, int(os.getenv('DB_POOL_RECYCLE', '3600'))),
            connect_args={
                'connect_timeout': max(3, int(os.getenv('DB_CONNECT_TIMEOUT', '10'))),
                'sslmode': sslmode,
                'options': '-c statement_timeout=10000 -c lock_timeout=3000 -c idle_in_transaction_session_timeout=15000',
                'application_name': 'vera-web-v2-auth',
            },
        )
        old = _engine
        _primary, _engine = primary, engine
        if old is not None:
            old.dispose()
        return engine
