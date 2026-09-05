from datetime import date
from pathlib import Path

from timesoft_sync_job import _timesoft_penalty_date_eligible
from vera_web_v2_attendance_query_perf import _keys_for_range


ROOT = Path(__file__).resolve().parents[1]


def test_attendance_query_always_includes_rolling_today_alias():
    keys = _keys_for_range(date(2026, 9, 5), date(2026, 9, 5))

    assert keys == [
        "timesoft_employee_checkin_today",
        "timesoft_employee_checkin_20260905",
        "timesoft_employee_checkin_20260905_raw",
    ]


def test_manual_auto_check_reprocesses_bounded_synced_history():
    today = date(2026, 9, 6)

    assert _timesoft_penalty_date_eligible(
        date(2026, 9, 5),
        today,
        include_synced_history=True,
    )


def test_scheduled_auto_check_keeps_today_only_safety_rule():
    today = date(2026, 9, 6)

    assert _timesoft_penalty_date_eligible(today, today)
    assert not _timesoft_penalty_date_eligible(date(2026, 9, 5), today)

    source = (ROOT / "timesoft_sync_job.py").read_text(encoding="utf-8")
    assert "include_synced_history=manual_run_requested" in source
    assert "dates = [today - timedelta(days=i) for i in range(SYNC_DAYS)]" in source


def test_auto_check_page_reports_runtime_config_mismatch():
    source = (ROOT / "web-v2/src/pages/AutoCheckPage.jsx").read_text(encoding="utf-8")

    assert "runtimeStatus !== String(cfg.status || '').toUpperCase()" in source
    assert "Tiến trình Auto Check gần nhất đang ở trạng thái" in source
    assert "Không có vi phạm Auto Check trong khoảng thời gian đã chọn." in source
