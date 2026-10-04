from datetime import date

import pytest

import vera_auto_check as auto_check
import vera_web_v2_department_attendance as departments


@pytest.mark.parametrize('role', ['locker', 'letan', 'tapvu', 'support', 'admin', 'quanly', '', 'unknown'])
@pytest.mark.parametrize('reason,minutes', [('Đi trễ không phép', 10), ('Ra ngoài vào muộn', 10), ('Nghỉ CUỐI TUẦN KHÔNG phép', 0)])
def test_shared_writer_skips_non_ktv_without_writes_or_schema(monkeypatch, role, reason, minutes):
    conn = object()
    def resolve(actual_conn, employee):
        assert actual_conn is conn and employee == 'Mạnh Đạt'
        return role
    monkeypatch.setattr(departments, 'employee_role', resolve)
    def unexpected(*args):
        pytest.fail('Excluded employee must never reach schema, event, leave or outbox writes')
    monkeypatch.setattr(auto_check, 'ensure_schema', unexpected)
    assert auto_check.save_violation(conn, work_date=date(2026, 10, 3), employee='Mạnh Đạt',
        reason_item={'name': reason, 'penalty': 1000000}, detail='test', source='test', minutes=minutes
    ) == (True, 'SKIP_ROLE_NOT_ELIGIBLE')


@pytest.mark.parametrize('role', ['leader', 'nhanvien'])
def test_ktv_continues_into_existing_writer_on_same_connection(monkeypatch, role):
    conn = object()
    monkeypatch.setattr(departments, 'employee_role', lambda actual_conn, employee: role)
    monkeypatch.setattr(departments, 'scheduled_assignment', lambda *args: None)
    class ReachedWriter(Exception):
        pass
    def reached(actual_conn):
        assert actual_conn is conn
        raise ReachedWriter
    monkeypatch.setattr(auto_check, 'ensure_schema', reached)
    with pytest.raises(ReachedWriter):
        auto_check.save_violation(conn, work_date=date(2026, 10, 3), employee='Test',
            reason_item={'name': 'Đi trễ không phép'}, detail='test', source='test', minutes=5)


@pytest.mark.parametrize('department', ['locker', 'letan', 'tapvu', 'support'])
def test_schedule_department_excludes_generic_employee_account(monkeypatch, department):
    monkeypatch.setattr(departments, 'employee_role', lambda *args: 'nhanvien')
    monkeypatch.setattr(departments, 'scheduled_assignment', lambda *args: {'department': department,
        'shift_code': 'Ca 2', 'overtime_shift': 'TC Ca 1', 'start_time': '09:30'})
    assert not auto_check.automatic_penalty_employee_eligible(object(), 'Mạnh Đạt', date(2026, 10, 3))
