"""Fail fast on board contention without retaining pooled waiters."""
from fastapi import HTTPException
from sqlalchemy import text


def acquire_state_lock(conn, key):
    # Transaction-scoped: PostgreSQL releases it on commit AND rollback.
    acquired = conn.execute(
        text("SELECT pg_try_advisory_xact_lock(hashtext(:key))"), {"key": key}
    ).scalar()
    if not acquired:
        raise HTTPException(
            status_code=503,
            detail="Bảng tua đang xử lý thao tác khác. Vui lòng thử lại sau vài giây.",
            headers={"Retry-After": "3"},
        )
