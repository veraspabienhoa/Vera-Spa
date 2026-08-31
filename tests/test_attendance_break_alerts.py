from datetime import date, datetime

from vera_web_v2_attendance_break_alerts import _deadline_payload, _parse_clock
from vera_web_v2_attendance_break_window import _enhance_break_payload


def test_thuy_vy_break_deadline_is_90_minutes_after_break_start():
    work_day = date(2026, 8, 31)

    def original(*args, **kwargs):
        return {
            "break_out": "15:53:31",
            "break_in": "",
            "break_actual_minutes": 0,
            "break_planned_minutes": 90,
            "break_enabled": True,
            "break_status": "Chưa đủ cặp chấm công",
        }

    result = _enhance_break_payload(
        original,
        [
            datetime(2026, 8, 31, 12, 58, 59),
            datetime(2026, 8, 31, 12, 59, 2),
            datetime(2026, 8, 31, 15, 53, 31),
            datetime(2026, 8, 31, 15, 53, 33),
        ],
        work_day=work_day,
        representative={},
        cfg={"break_enabled": True, "break_planned_minutes": 90, "faceid_cluster_minutes": 10},
    )

    assert result["break_out"] == "15:53:31"
    assert result["break_in"] == ""
    assert result["break_return_deadline"] == "17:23:31"
    assert "17:23:31" in result["break_status"]
    assert "20:00" not in result["break_status"]


def test_completed_break_late_time_is_measured_from_dynamic_deadline():
    payload = _deadline_payload(
        work_day=date(2026, 8, 31),
        break_out=datetime(2026, 8, 31, 15, 53, 31),
        break_in=datetime(2026, 8, 31, 17, 30, 31),
        planned_minutes=90,
        source="TimeSoft FaceID",
    )

    assert payload["break_return_deadline"] == "17:23:31"
    assert payload["break_return_late_minutes"] == 7
    assert payload["break_actual_minutes"] == 97


def test_tourvera_clock_parser_accepts_excel_time_fraction_and_clock_text():
    work_day = date(2026, 8, 31)
    assert _parse_clock("15:53:31", work_day) == datetime(2026, 8, 31, 15, 53, 31)
    parsed = _parse_clock(0.5, work_day)
    assert parsed == datetime(2026, 8, 31, 12, 0, 0)
