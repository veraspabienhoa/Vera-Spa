from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def source(name: str) -> str:
    return (ROOT / name).read_text(encoding="utf-8")


def test_auto_event_has_retryable_employee_notification_outbox():
    core = source("vera_auto_check.py")
    notifier = source("vera_auto_penalty_notifications.py")

    assert "employee_notify_claimed_at" in core
    assert "employee_notify_attempted_at" in core
    assert "employee_notified_at" in core
    assert "WHERE status='added' AND employee_notified_at IS NULL" in notifier
    assert "FOR UPDATE SKIP LOCKED" in notifier
    assert "employee_notified_at=CASE WHEN :sent > 0 OR :suppressed THEN NOW()" in notifier


def test_committed_penalty_outbox_is_drained_by_background_worker():
    sync = source("timesoft_sync_job.py")
    break_return = source("vera_web_v2_break_return_penalty.py")
    outside = source("vera_web_v2_outside_leave_rule.py")

    assert "penalty_notifications.notify_pending(engine)" in sync
    # Projection runs inside callers' transactions and must not synchronously
    # acquire another connection or send network requests before commit.
    assert "notify_pending(" not in break_return
    assert "notify_pending(" not in outside


def test_notification_identifies_penalty_and_employee_without_duplicates():
    notifier = source("vera_auto_penalty_notifications.py")

    assert '"kind": "auto-penalty-recorded"' in notifier
    assert '"VERA SPA · Hệ thống đã ghi phạt"' in notifier
    assert 'f"vera-auto-penalty-{event[\'id\']}"' in notifier
    assert "Mức phạt" in notifier
    assert "Nhân viên chưa bật thông báo Web Push." in notifier
