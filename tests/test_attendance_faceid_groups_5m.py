from datetime import date, datetime
from types import SimpleNamespace

import vera_web_v2_attendance_break_window as break_window
import vera_web_v2_attendance_v42 as attendance


class _DummyApp:
    def __init__(self):
        self.state = SimpleNamespace()

    def get(self, _path):
        def decorator(func):
            return func
        return decorator


def _install_once():
    app = _DummyApp()
    break_window.install_attendance_break_window(app)


def _dt(clock: str) -> datetime:
    return datetime.strptime(f"31/08/2026 {clock}", "%d/%m/%Y %H:%M:%S")


def _cfg():
    return {
        "faceid_cluster_minutes": 10,  # legacy config must be overridden to 5
        "break_planned_minutes": 90,
        "break_enabled": True,
        "break_restricted_reason": "",
    }


def _representative():
    return {"StartWorkTime": "10:00", "EndWorkTime": "23:00"}


def test_scans_inside_five_minutes_are_one_group_using_first_scan():
    _install_once()
    values = [_dt("15:30:00"), _dt("15:32:10"), _dt("15:35:00"), _dt("17:00:00"), _dt("17:04:59")]
    grouped = attendance._cluster_punches(values, 10)
    assert grouped == [_dt("15:30:00"), _dt("17:00:00")]


def test_van_anh_today_is_break_out_154616_and_return_161714():
    _install_once()
    result = attendance._break_from_punches(
        [_dt("09:59:40"), _dt("15:46:16"), _dt("16:17:14")],
        work_day=date(2026, 8, 31),
        representative=_representative(),
        cfg=_cfg(),
    )
    assert result["break_out"] == "15:46:16"
    assert result["break_in"] == "16:17:14"
    assert result["break_actual_minutes"] == 31
    assert result["faceid_group_minutes"] == 5


def test_thuy_vy_duplicate_scans_form_only_two_groups_and_first_break_scan_wins():
    _install_once()
    result = attendance._break_from_punches(
        [_dt("12:58:59"), _dt("12:59:02"), _dt("15:53:31"), _dt("15:53:33")],
        work_day=date(2026, 8, 31),
        representative={"StartWorkTime": "13:00", "EndWorkTime": "23:59"},
        cfg=_cfg(),
    )
    assert result["faceid_check_in"] == "12:58:59"
    assert result["break_out"] == "15:53:31"
    assert result["break_in"] == ""
    assert result["break_started"] is True
