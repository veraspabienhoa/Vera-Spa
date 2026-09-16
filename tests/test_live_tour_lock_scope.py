from pathlib import Path

SOURCE = Path(__file__).parents[1] / "vera_web_v2_live_tour.py"

def source(): return SOURCE.read_text(encoding="utf-8")

def test_background_projection_reschedules_when_operator_holds_lock():
    body = source()
    apply = body[body.index("    def apply_projection"):body.index("    def scheduled_projection") ]
    worker = body[body.index("    def projection_worker"):body.index("    def start_scheduler") ]
    assert "if not try_state_lock(conn, STATE_LOCK):" in apply
    assert "acquire_state_lock(conn, STATE_LOCK)" not in apply
    assert "job_queue.reschedule" in worker

def test_permissions_are_resolved_before_mutation_lock():
    body = source()
    action = body[body.index('@app.post("/v2/live-tour/action")'):body.index('@app.get("/v2/live-tour/projection-queue/health")')]
    assert action.index("grants = permissions(conn, ident)") < action.index("acquire_state_lock(conn, STATE_LOCK)")

def test_request_actions_never_run_attendance_or_leave_projection_under_board_lock():
    body = source()
    action = body[body.index('@app.post("/v2/live-tour/action")'):body.index('@app.get("/v2/live-tour/projection-queue/health")')]
    locked = action[action.index("acquire_state_lock(conn, STATE_LOCK)"):]
    assert "read_state_without_projection(conn, now, for_update=True)" in locked
    assert "attendance.read(" not in locked
    assert "FROM leave_records" not in locked
    assert "_employee_directory(conn" not in locked

def test_manual_daily_refresh_enqueues_instead_of_projecting_inline():
    action = source().split('@app.post("/v2/live-tour/action")', 1)[1].split('@app.get("/v2/live-tour/projection-queue/health")', 1)[0]
    assert 'action == "sync_daily_status"' in action
    assert "job_queue.enqueue_conn(" in action
