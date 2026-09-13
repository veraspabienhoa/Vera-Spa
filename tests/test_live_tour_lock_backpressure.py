from pathlib import Path
from unittest.mock import Mock

import pytest
from fastapi import HTTPException

from vera_web_v2_live_tour_lock import acquire_state_lock


def test_lock_acquired_uses_caller_connection():
    conn = Mock()
    conn.execute.return_value.scalar.return_value = True
    acquire_state_lock(conn, "board")
    sql, params = conn.execute.call_args.args
    assert "pg_try_advisory_xact_lock" in str(sql)
    assert params == {"key": "board"}
    conn.commit.assert_not_called()
    conn.close.assert_not_called()


def test_busy_lock_returns_retryable_error_without_waiting():
    conn = Mock()
    conn.execute.return_value.scalar.return_value = False
    with pytest.raises(HTTPException) as caught:
        acquire_state_lock(conn, "board")
    assert caught.value.status_code == 503
    assert caught.value.headers == {"Retry-After": "3"}
    assert conn.execute.call_count == 1


def test_all_board_locks_use_nonblocking_guard():
    source = (Path(__file__).parents[1] / "vera_web_v2_live_tour.py").read_text()
    assert "pg_advisory_xact_lock(" not in source
    assert source.count("acquire_state_lock(conn, STATE_LOCK)") == 10
