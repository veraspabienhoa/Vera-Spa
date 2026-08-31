from datetime import date, datetime

import vera_web_v2_attendance_v42 as attendance
from vera_web_v2_attendance_break_window import _enhance_break_payload, _pick_break_pair


def _dt(value: str) -> datetime:
    return datetime.strptime(value, "%d/%m/%Y %H:%M:%S")


def _cfg():
    return {
        "break_enabled": True,
        "break_planned_minutes": 90,
        "faceid_cluster_minutes": 10,
        "break_restricted_reason": "",
    }


def test_duplicate_faceid_at_1553_is_visible_as_break_start_before_return_scan():
    work_day = date(2026, 8, 31)
    punches = [
        _dt("31/08/2026 12:58:59"),
        _dt("31/08/2026 12:59:02"),
        _dt("31/08/2026 15:53:31"),
        _dt("31/08/2026 15:53:33"),
    ]

    result = _enhance_break_payload(
        attendance._break_from_punches,
        punches,
        work_day=work_day,
        representative={},
        cfg=_cfg(),
    )

    assert result["break_out"] == "15:53:31"
    assert result["break_in"] == ""
    assert result["break_actual_minutes"] == 0
    assert result["break_planned_minutes"] == 90
    assert result["break_detail"] == "Bắt đầu nghỉ giữa ca 31/08/2026 15:53:31"
    assert result["break_window_start"] == "15:00:00"
    assert result["break_return_deadline"] == "20:00:00"
    assert result["break_started"] is True


def test_break_pair_must_start_from_1500_and_return_after_2000_is_kept_for_late_status():
    values = [
        _dt("31/08/2026 14:50:00"),
        _dt("31/08/2026 15:53:31"),
        _dt("31/08/2026 20:02:00"),
    ]
    chosen = _pick_break_pair(values, 90, 10)
    assert chosen is not None
    assert chosen[0].strftime("%H:%M:%S") == "15:53:31"
    assert chosen[1].strftime("%H:%M:%S") == "20:02:00"
