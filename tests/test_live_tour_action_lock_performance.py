from pathlib import Path

def src():
    return Path("vera_web_v2_live_tour.py").read_text(encoding="utf-8")

def test_operator_actions_use_projection_free_snapshot():
    block = src().split("projection_free_actions = {", 1)[1].split("}", 1)[0]
    for action in ("start", "start_room", "finish_to_pending", "finish_room"):
        assert f'"{action}"' in block

def test_scheduler_reads_attendance_before_board_lock():
    block = src().split("def scheduled_projection():", 1)[1].split("def start_scheduler():", 1)[0]
    assert block.index("attendance.read(") < block.index("try_state_lock(conn, STATE_LOCK)")
    assert "attendance_records=projection_records" in block

def test_legacy_test_writers_are_compatible():
    assert "def _write_state_compat(" in src()
