from datetime import date, datetime, timedelta
import json
import pytest

from vera_schedule_attendance_window import attendance_window
import vera_web_v2_attendance_query_perf as attendance
import vera_missing_checkin_notifications as alerts
import vera_facegate_attendance as fg

DAY = date(2026, 10, 3)


def schedule(**changes):
    return {"work_date": DAY, "employee_username": "Locker Test", "employee_name": "Locker Test",
            "department": "locker", "shift_code": "Ca 2", "start_time": "17:30", "end_time": "01:30",
            "overtime_shift": "TC Ca 1", "overtime_start_time": "09:30", "overtime_end_time": "17:30", **changes}


@pytest.mark.parametrize("changes, expected", [
    ({}, ("09:30", "01:30")),
    ({"shift_code": "Ca 1", "start_time": "09:30", "end_time": "17:30", "overtime_shift": "TC Ca 2",
      "overtime_start_time": "17:30", "overtime_end_time": "01:30"}, ("09:30", "01:30")),
    ({"overtime_shift": ""}, ("17:30", "01:30")),
    ({"shift_code": "Nghỉ"}, ("", "")),
    ({"overtime_start_time": ""}, ("17:30", "01:30")),
    ({"overtime_shift": "Từ giờ tới giờ", "overtime_start_time": "01:30", "overtime_end_time": "03:30"}, ("17:30", "03:30")),
    ({"overtime_shift": "Từ giờ tới giờ", "overtime_start_time": "08:00", "overtime_end_time": "10:00"}, ("08:00", "01:30")),
])
def test_effective_window(changes, expected):
    assert attendance_window(schedule(**changes)) == expected


class Connection:
    def __init__(self, rows):
        self.rows = rows
        self.statements = []
    def execute(self, statement, parameters):
        self.statements.append(str(statement))
        return self
    def mappings(self):
        return self
    def all(self):
        return self.rows


def test_attendance_and_notification_readers_use_same_overtime_window():
    conn = Connection([schedule()])
    result = attendance._schedule_map(conn, DAY, DAY)[(DAY, "locker test")]
    alert = alerts._scheduled_rows(conn, DAY)[0]
    assert attendance._vera_shift_fields({"role": "locker"}, DAY, [], result) == ("Ca 2", "09:30", "01:30")
    assert (alert["start_time"], alert["end_time"]) == ("09:30", "01:30")
    assert all("ot.department=ws.department" in statement and "TC Ca 1" in statement for statement in conn.statements)
    assert alerts._alert_ready(has_leave=False, has_faceid=False,
        current=datetime(2026, 10, 3, 9, 46), shift_start=alerts._clock(DAY, alert["start_time"]))


def test_morning_overtime_punch_is_accepted_and_midnight_exit_stays_previous_day():
    conn = Connection([schedule()])
    row = attendance._schedule_map(conn, DAY, DAY)[(DAY, "locker test")]
    profile = {"username": "Locker Test", "full_name": "Locker Test", "role": "locker"}
    ref = {"file_type": 0, "file_index": 1, "file_position": 1420}
    address = "192.0.2.1"
    mapping = {"username": "Locker Test", "registration_ref": ref, "confirmed_by": "admin", "device_address": address}
    def event(day, clock, eid):
        return {"event_id": eid, "occurred_at": f"{day}T{clock}+07:00", "payload_json": json.dumps({
            "registration_ref": ref, "device_address": address, "status_code": "1", "type_code": "0"})}
    def resolve(profile, day):
        return attendance._vera_shift_fields(profile, day, [], row)
    rows, issues, _ = fg.adapt_events([event(DAY, "09:32:05", "1"),
        event(DAY+timedelta(days=1), "01:14:09", "2")], [mapping], [profile], address, DAY, DAY, resolve)
    assert not issues
    assert [r["WorkDateStr"] for r in rows] == ["03/10/2026", "03/10/2026"]
    assert rows[0]["MachineTimeCheckInStr"].endswith("09:32:05")
    assert alerts._faceid_employees(__import__("pandas").DataFrame(rows), {}) == {"locker test"}
    assert not alerts._alert_ready(has_leave=False, has_faceid=True,
        current=datetime(2026, 10, 3, 18, 0), shift_start=datetime(2026, 10, 3, 9, 30))
