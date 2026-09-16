from pathlib import Path

def src():
    return Path("vera_web_v2_live_tour.py").read_text(encoding="utf-8")

def test_all_interactive_actions_use_canonical_snapshot_only():
    action = src().split('@app.post("/v2/live-tour/action")', 1)[1].split('@app.get("/v2/live-tour/projection-queue/health")', 1)[0]
    assert "read_state_without_projection(conn, now, for_update=True)" in action
    assert "projection_free_actions" not in action

def test_projection_reads_inputs_before_board_lock():
    body = src()
    inputs = body.split("def projection_inputs(now):", 1)[1].split("def apply_projection", 1)[0]
    apply = body.split("def apply_projection", 1)[1].split("def scheduled_projection", 1)[0]
    assert "attendance.read(" in inputs
    assert "_employee_directory(" in inputs
    assert "FROM leave_records" in inputs
    assert "STATE_LOCK" not in inputs
    assert "try_state_lock(conn, STATE_LOCK)" in apply
    assert "attendance.read(" not in apply

def test_projection_is_queued_every_five_minutes():
    body = src()
    assert "PROJECTION_REFRESH_SECONDS = 300" in body
    assert "scheduler_stop.wait(PROJECTION_REFRESH_SECONDS)" in body
    assert "job_queue.claim_one(engine_instance, PROJECTION_QUEUE)" in body

def test_legacy_test_writers_are_compatible():
    assert "def _write_state_compat(" in src()
