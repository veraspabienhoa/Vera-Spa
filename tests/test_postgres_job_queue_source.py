from pathlib import Path

def test_claim_commits_before_slow_work_and_uses_skip_locked():
    source = Path("vera_postgres_job_queue.py").read_text(encoding="utf-8")
    claim = source.split("def claim_one", 1)[1].split("def mark_done", 1)[0]
    assert "FOR UPDATE SKIP LOCKED" in claim
    assert "status='processing'" in claim
    assert "handler" not in claim

def test_live_tour_queue_has_short_input_and_apply_phases():
    source = Path("vera_web_v2_live_tour.py").read_text(encoding="utf-8")
    inputs = source.split("def projection_inputs", 1)[1].split("def apply_projection", 1)[0]
    apply = source.split("def apply_projection", 1)[1].split("def scheduled_projection", 1)[0]
    assert "STATE_LOCK" not in inputs
    assert "try_state_lock(conn, STATE_LOCK)" in apply
    assert "directory_records=directory" in apply
    assert "leave_records=leaves" in apply

def test_timesoft_has_one_sync_per_scheduler_invocation():
    source = Path("timesoft_snapshot_job.py").read_text(encoding="utf-8")
    assert "return int(ts.run_sync())" in source
    assert "_fast_checkin_tail" not in source
    cloud = Path("cloudbuild.yaml").read_text(encoding="utf-8")
    assert "TIMESOFT_FAST_CHECKIN_SECONDS" not in cloud
    assert "TIMESOFT_FAST_CHECKIN_WINDOW_SECONDS" not in cloud
