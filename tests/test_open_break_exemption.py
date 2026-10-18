from datetime import date, datetime
from types import SimpleNamespace
import pytest
import vera_open_break_exemption as rule

DAY = date(2026, 10, 18)
OUT = datetime(2026, 10, 18, 15, 0)


def evidence(**changes):
    return dict({'shift': 'Ca 1', 'break_out': '15:00:00', 'break_in': '',
                 'evidence_source': 'facegate', 'attendance_fine_evidence_ready': True,
                 'punch_datetimes': ['2026-10-18T10:00:00', '2026-10-18T15:00:00']}, **changes)


def leave(**changes):
    return dict({'record_uid': 'manual', 'created_at': datetime(2026, 10, 18, 16),
        'leave_reason': 'Về sớm KHÔNG phép', 'source_sheet_id': 'sheet',
        'payload': {rule.MARKER: {'role': 'letan', 'registered_at': '2026-10-18T16:00:00+07:00'}}}, **changes)


@pytest.mark.parametrize('shift', ['Ca 1', 'Ca 2'])
@pytest.mark.parametrize('role', ['admin', 'quanly', 'letan'])
def test_both_shifts_and_authorized_manual_actors(shift, role):
    row = leave(payload={rule.MARKER: {'role': role, 'registered_at': '2026-10-18T16:00:00+07:00'}})
    assert rule.qualifying_break(evidence(shift=shift), [row], DAY) == OUT


@pytest.mark.parametrize('change', [
    {'break_in': '16:00:00'}, {'punch_datetimes': []}, {'shift': 'Ca 3'},
    {'punch_datetimes': ['2026-10-18T10:00:00', '2026-10-18T15:00:00', '2026-10-18T17:00:00']},
    {'attendance_fine_evidence_ready': False}, {'attendance_evidence_issues': ['stale']},
    {'evidence_source': 'tour'},
])
def test_incomplete_or_returned_break_not_exempt(change):
    assert rule.qualifying_break(evidence(**change), [leave()], DAY) is None


@pytest.mark.parametrize('change', [
    {'payload': {}}, {'leave_reason': 'Về sớm CÓ phép'},
    {'created_at': datetime(2026, 10, 18, 14)},
    {'payload': {rule.MARKER: {'role': 'nhanvien', 'registered_at': '2026-10-18T16:00:00+07:00'}}},
    {'payload': {rule.MARKER: {'role': 'admin', 'registered_at': '2026-10-19T16:00:00+07:00'}}},
])
def test_no_inferred_departure_or_untrusted_confirmation(change):
    assert rule.qualifying_break(evidence(), [leave(**change)], DAY) is None


@pytest.mark.parametrize('reason', ['Nghỉ nửa ngày', 'Nghỉ CÓ phép', 'Nghỉ chế độ', 'Đi trễ CÓ phép', 'Hỗ trợ'])
def test_any_other_schedule_blocks_exemption(reason):
    assert rule.qualifying_break(evidence(), [leave(), leave(leave_reason=reason, payload={})], DAY) is None


def test_automatic_violations_do_not_count_as_leave_schedule():
    rows = [leave(), leave(leave_reason='Đi trễ nhỏ hơn hoặc bằng 30 phút', automatic=True)]
    assert rule.qualifying_break(evidence(), rows, DAY) == OUT


def test_weekend_confirmation_and_exact_break_event():
    assert rule.qualifying_break(evidence(), [leave(leave_reason='Về sớm CUỐI TUẦN KHÔNG phép')], DAY) == OUT
    assert rule.matches_event('Ra ngoài chỉ có dữ liệu một lần', 'Giờ ra 15:00:00 · test', OUT)
    assert not rule.matches_event('Ra ngoài vào muộn dưới 30 phút', 'Giờ ra 14:00:00', OUT)
    assert not rule.matches_event('Về sớm KHÔNG phép', 'Giờ ra 15:00:00', OUT)
    assert not rule.matches_event('Ra ngoài chỉ có dữ liệu một lần', 'thiếu giờ vào', OUT)


def test_revoke_only_exact_linked_outside_event():
    calls = []
    class Conn:
        def execute(self, sql, params):
            calls.append((str(sql), params))
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: [
                {'id': 1, 'reason': 'Ra ngoài chỉ có dữ liệu một lần', 'detail': 'Giờ ra 15:00:00', 'leave_record_uid': 'out'},
                {'id': 2, 'reason': 'Về sớm KHÔNG phép', 'detail': 'Giờ ra 15:00:00', 'leave_record_uid': 'early'},
                {'id': 3, 'reason': 'Ra ngoài vào muộn dưới 30 phút', 'detail': 'Giờ ra 13:00:00', 'leave_record_uid': 'other'},
            ]))
    assert rule.revoke(Conn(), 'worker', DAY, OUT) == 1
    assert [params['uid'] for sql, params in calls if sql.startswith('DELETE')] == ['out']
    assert "r.updated_by=e.source" in calls[0][0]


def test_writer_guard_does_not_recreate_exempt_event(monkeypatch):
    import vera_auto_check as auto
    monkeypatch.setattr(auto, 'automatic_penalty_employee_eligible', lambda *a: True)
    monkeypatch.setattr(rule, 'exemption', lambda *a: OUT)
    class Conn:
        def execute(self, *a):
            raise AssertionError('No financial write for exempt event')
    assert auto.save_violation(Conn(), work_date=DAY, employee='worker',
        reason_item={'name': 'Ra ngoài chỉ có dữ liệu một lần'},
        detail='Giờ ra 15:00:00', source='AUTO', minutes=0) == (True, 'SKIP_OPEN_BREAK_EARLY_DEPARTURE')


def test_stale_evidence_keeps_durable_retry(monkeypatch):
    import vera_facegate_runtime as runtime
    from vera_leave_penalty_recheck import EvidencePending
    monkeypatch.setattr(rule, 'registrations', lambda *a: [leave()])
    monkeypatch.setattr(runtime, 'records', lambda *a: [dict(employee_name='worker', attendance_fine_evidence_ready=False)])
    with pytest.raises(EvidencePending):
        rule.reconcile(object(), 'worker', DAY)


def test_approved_benefit_leave_blocks_even_without_daily_row(monkeypatch):
    import vera_holiday_leave as holiday
    monkeypatch.setattr(rule, 'registrations', lambda *a: [leave()])
    monkeypatch.setattr(holiday, 'approved_day', lambda *a: True)
    assert rule.exemption(object(), 'worker', DAY, evidence()) is None


def test_untrusted_role_cannot_stamp_or_enqueue():
    class Conn:
        def execute(self, *a):
            raise AssertionError('Untrusted actor cannot stamp exemption')
    rule.register(Conn(), leave(), SimpleNamespace(role='nhanvien'))


def test_worker_without_ui_break_wrapper_uses_canonical_faceid_groups():
    assert rule.qualifying_break(evidence(break_out=''), [leave()], DAY) == OUT


def test_no_manual_confirmation_does_not_require_auto_event_schema():
    calls = []
    class Conn:
        def execute(self, sql, params):
            calls.append(str(sql))
            assert 'vera_auto_check_event' not in str(sql)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    assert rule.exemption(Conn(), 'worker', DAY) is None
    assert len(calls) == 1
