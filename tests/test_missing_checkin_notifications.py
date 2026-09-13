from datetime import date, datetime, timedelta
from pathlib import Path

import pandas as pd

import vera_missing_checkin_notifications as alerts


ROOT = Path(__file__).resolve().parents[1]


class _MappingResult:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _AudienceConnection:
    def __init__(self, rows):
        self.rows = rows

    def execute(self, _statement, _params):
        return _MappingResult(self.rows)


def test_faceid_employee_alias_is_canonicalized():
    frame = pd.DataFrame([{
        "EmployeeName": "Lễ Tân A",
        "MachineTimeStr": "03/09/2026 09:29:58",
    }])
    assert alerts._faceid_employees(frame, {"le tan a": "letan.a"}) == {"letan.a"}


def test_blank_summary_row_does_not_count_as_faceid():
    frame = pd.DataFrame([{"EmployeeName": "Locker A", "MachineTimeCheckInStr": ""}])
    assert alerts._faceid_employees(frame, {"locker a": "locker.a"}) == set()


def test_checkout_summary_is_not_shift_checkin():
    frame = pd.DataFrame([{'EmployeeName': 'Ngọc Như', 'MachineTimeCheckOutStr': '13/09/2026 00:30:00'}])
    assert alerts._faceid_employees(frame, {}) == set()


def test_staff_without_timesoft_rows_uses_rotating_roster():
    definitions = [{'Tên ca': 'Ca 1', 'Ca chính': 'Ca 1', 'Giờ bắt đầu': '09:00'},
                   {'Tên ca': 'Ca 2', 'Ca chính': 'Ca 2', 'Giờ bắt đầu': '13:00'}]
    conn = _AudienceConnection([{'username': 'ngocnhu', 'full_name': 'Ngọc Như', 'role': 'nhanvien',
        'payload': {}, 'work_shift': 'Ca 1', 'rotation_cycle': '7 ngày', 'shift_start_date': '2026-09-07', 'shift_definitions': definitions}])
    assert alerts._staff_scheduled_rows(conn, date(2026, 9, 13))[0]['start_time'] == '09:00'
    assert alerts._staff_scheduled_rows(conn, date(2026, 9, 14))[0]['start_time'] == '13:00'


def test_missing_alert_visible_without_push_key_and_cleared_after_checkin(monkeypatch):
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *_): pass
    class Engine:
        def connect(self): return Connection()
        def begin(self): return Connection()
    monkeypatch.setattr(alerts, '_scheduled_rows', lambda *_: [])
    monkeypatch.setattr(alerts, '_staff_scheduled_rows', lambda *_: [{'employee_username': 'linhdan', 'employee_name': 'Linh Đan', 'department': 'nhanvien', 'shift_code': 'Ca 1', 'start_time': '09:00'}])
    monkeypatch.setattr(alerts, '_delivery_state', lambda *_: {})
    monkeypatch.setattr(alerts, '_has_leave_schedule', lambda *_: False)
    monkeypatch.setattr(alerts, '_audience_subscriptions', lambda *_: [])
    monkeypatch.setattr(alerts, '_vault_secret', lambda *_: '')
    saved = []
    monkeypatch.setattr(alerts, '_mark_delivery_state', lambda conn, key, data, sent: saved.append(data))
    frame = pd.DataFrame([{'EmployeeName': 'Other', 'MachineTimeCheckInStr': '13/09/2026 09:00:00'}])
    alerts.notify_missing_scheduled_checkins(Engine(), frame, date(2026, 9, 13), {}, datetime(2026, 9, 13, 9, 16))
    assert saved[-1]['alerts'][0]['employee'] == 'linhdan'
    frame = pd.DataFrame([{'EmployeeName': 'Linh Đan', 'MachineTimeCheckInStr': '13/09/2026 09:17:00'}])
    alerts.notify_missing_scheduled_checkins(Engine(), frame, date(2026, 9, 13), {'linh dan': 'linhdan'}, datetime(2026, 9, 13, 9, 18))
    assert saved[-1]['alerts'] == []


def test_timesoft_schedule_covers_employee_and_leader_without_faceid():
    frame = pd.DataFrame([
        {"EmployeeName": "Nhân viên A", "WorkTimeName": "Ca 1", "StartWorkTime": "09:30"},
        {"EmployeeName": "Leader B", "WorkTimeName": "Ca 2", "StartWorkTime": "12:30"},
    ])
    schedules = alerts._timesoft_scheduled_rows(
        frame, {"nhan vien a": "nhanvien.a", "leader b": "leader.b"},
    )
    assert [(item["employee_username"], item["start_time"]) for item in schedules] == [
        ("nhanvien.a", "09:30"), ("leader.b", "12:30"),
    ]


def test_postgres_schedule_wins_when_timesoft_has_same_employee():
    timesoft = [{"employee_username": "locker.a", "start_time": "09:00", "shift_code": "TS"}]
    postgres = [{"employee_username": "Locker.A", "start_time": "09:30", "shift_code": "Ca 1"}]
    assert alerts._merge_schedules(timesoft, postgres) == postgres


def test_alert_requires_all_three_if_conditions_at_the_same_time():
    start = datetime(2026, 9, 8, 9, 30)
    after_deadline = datetime(2026, 9, 8, 9, 46)
    assert alerts._alert_ready(
        has_leave=False, has_faceid=False, current=after_deadline, shift_start=start,
    )
    assert not alerts._alert_ready(
        has_leave=True, has_faceid=False, current=after_deadline, shift_start=start,
    )
    assert not alerts._alert_ready(
        has_leave=False, has_faceid=True, current=after_deadline, shift_start=start,
    )
    assert not alerts._alert_ready(
        has_leave=False, has_faceid=False,
        current=datetime(2026, 9, 8, 9, 45), shift_start=start,
    )


def test_clock_and_event_key_are_stable():
    work_day = date(2026, 9, 3)
    assert alerts._clock(work_day, "09:30").isoformat() == "2026-09-03T09:30:00"
    assert alerts._clock(work_day, "không có") is None
    assert alerts._event_key(work_day, "Locker A", "Ca 1") == alerts._event_key(work_day, " locker a ", "ca 1")


def test_alert_is_wired_outside_auto_check_and_into_fast_tail():
    sync_source = (ROOT / "timesoft_sync_job.py").read_text(encoding="utf-8")
    snapshot_source = (ROOT / "timesoft_snapshot_job.py").read_text(encoding="utf-8")
    call = "missing_checkin_notifications.notify_missing_scheduled_checkins"
    assert sync_source.index(call) < sync_source.index("# Auto Check PostgreSQL-only")
    assert call in snapshot_source
    alert_source = (ROOT / "vera_missing_checkin_notifications.py").read_text(encoding="utf-8")
    assert "THRESHOLD_MINUTES = 15" in alert_source
    assert "import vera_auto_check" not in alert_source
    assert "import vera_auto_penalty_notifications" not in alert_source
    assert "auto_check." not in alert_source
    assert "department_attendance" not in alert_source
    assert "notifications_enabled" not in alert_source
    assert "REQUIRED_AUDIENCES = frozenset" in alert_source
    assert '{"employee", "letan", "quanly", "admin"}' in alert_source
    assert "current > shift_start + timedelta(minutes=THRESHOLD_MINUTES)" in alert_source
    assert "https://app.veraspa.vn/" in alert_source


def test_leave_check_excludes_auto_check_rows_at_the_query_boundary():
    source = (ROOT / "vera_missing_checkin_notifications.py").read_text(encoding="utf-8")
    leave_check = source.split("def _has_leave_schedule", 1)[1].split("def _audience_subscriptions", 1)[0]
    assert "FROM leave_records" in leave_check
    assert "COALESCE(source_sheet_id,'') <> 'postgres:auto_check'" in leave_check


def test_notification_audience_is_exactly_employee_reception_manager_and_admin():
    source = (ROOT / "vera_missing_checkin_notifications.py").read_text(encoding="utf-8")
    audience = source.split("def _audience_subscriptions", 1)[1].split("def _event_key", 1)[0]
    assert "s.employee_username" in audience
    assert "('admin','letan','quanly')" in audience


def test_audience_classification_supports_employee_reception_manager_and_admin():
    rows = [
        {"subscription_id": "employee", "employee_username": "locker.a", "profile_role": "nhanvien"},
        {"subscription_id": "reception", "employee_username": "letan.a", "profile_role": "letan"},
        {"subscription_id": "admin", "employee_username": "admin.a", "profile_role": "admin"},
        {"subscription_id": "manager", "employee_username": "manager.a", "profile_role": "quanly"},
        # If the absent employee is also an admin, one successful device covers both audiences.
        {"subscription_id": "employee-admin", "employee_username": "locker.a", "profile_role": "admin"},
    ]
    subscriptions = alerts._audience_subscriptions(
        _AudienceConnection(rows), "locker.a", "Locker A",
    )
    assert [(item["subscription_id"], item["audiences"]) for item in subscriptions] == [
        ("employee", ["employee"]),
        ("reception", ["letan"]),
        ("admin", ["admin"]),
        ("manager", ["quanly"]),
        ("employee-admin", ["admin", "employee"]),
    ]


def test_timezone_aware_now_can_be_compared_to_schedule_clock():
    # Production passes datetime.now(VN_TZ); the notifier intentionally makes
    # it naive because TimeSoft and work-schedule clocks are local wall time.
    aware = datetime.fromisoformat("2026-09-03T09:45:00+07:00")
    assert aware.replace(tzinfo=None) >= alerts._clock(date(2026, 9, 3), "09:30")


def test_in_app_missing_checkins_respect_viewer_and_freshness():
    from types import SimpleNamespace
    now = datetime(2026, 9, 13, 9, 20)
    data = {'work_date': '2026-09-13', 'checked_at': '2026-09-13T09:16:00',
            'alerts': [{'employee': 'linhdan'}, {'employee': 'ngocnhu'}]}
    class Conn:
        def execute(self, query, params):
            assert params['key'] == 'current_alerts:2026-09-13'
            return self
        def mappings(self): return self
        def all(self): return [{'value_json': data}]
    assert len(alerts.viewer_missing_checkins(Conn(), SimpleNamespace(role='letan'), now)) == 2
    assert alerts.viewer_missing_checkins(Conn(), SimpleNamespace(role='nhanvien', employee_username='linhdan'), now) == [{'employee': 'linhdan'}]
    assert alerts.viewer_missing_checkins(Conn(), SimpleNamespace(role='nhanvien', employee_username='other'), now) == []
    assert alerts.viewer_missing_checkins(Conn(), SimpleNamespace(role='admin'), now + timedelta(minutes=11)) == []
