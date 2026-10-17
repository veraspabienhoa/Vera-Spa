from contextlib import nullcontext
from datetime import datetime

import pandas as pd
import pytest
import vera_auto_check as auto
import timesoft_sync_job as sync
from vera_attendance_rules import supported_late_minutes


@pytest.mark.parametrize('raw,eligible', [(121 + 5/60, False), (124 + 59/60, False), (125, True)])
def test_supported_arrival_threshold_and_cleaning(monkeypatch, raw, eligible):
    adjusted = supported_late_minutes(raw, 120)
    reason = auto.ARRIVAL_BAND_REASONS[0]
    assert auto.automatic_late_penalty_eligible(reason, adjusted) is eligible
    saved = []
    monkeypatch.setattr(auto, 'save_violation', lambda *a, **kw: (saved.append(kw) or (True, 'ADDED')))
    catalog = {auto._norm(auto.CLEANING_CA1_REASON): {'name': auto.CLEANING_CA1_REASON, 'days': 0, 'type': 'Vi phạm'}}
    auto.save_arrival_cleaning_violation(None, work_date=datetime.now().date(), employee='Test', catalog=catalog, shift='Ca 1', detail='', minutes=adjusted)
    assert bool(saved) is eligible


@pytest.mark.parametrize('raw', [121 + 5/60, 124 + 59/60])
def test_direct_sync_revokes_supported_under_five_minute_fines(monkeypatch, raw):
    today = datetime.now(sync.VN_TZ).date()
    conn = object()
    class Engine:
        def begin(self): return nullcontext(conn)
    monkeypatch.setattr(sync, 'canonical_employee', lambda *_: 'Test')
    monkeypatch.setattr(sync.department_attendance, 'employee_role', lambda *_: 'nhanvien')
    monkeypatch.setattr(sync, '_parse_minutes_late', lambda _: raw)
    monkeypatch.setattr(auto, 'registered_late_for_day', lambda *_: ([], 0, ''))
    monkeypatch.setattr(auto, 'late_support_for_day', lambda *_: (['Hỗ trợ'], 120, 'Hỗ trợ'))
    revoked = []
    monkeypatch.setattr(auto, 'revoke_wrong_late_penalty', lambda *a, **kw: (revoked.append(kw) or 2))
    monkeypatch.setattr(auto, 'save_violation', lambda *a, **kw: pytest.fail('must not create a fine'))
    result = sync.process_timesoft_penalties(Engine(), {'threshold_minutes': 5}, {}, {}, [(today, pd.DataFrame([{'EmployeeName': 'Test'}]))])
    assert result['added'] == 0
    assert result['skipped'] == 1
    assert len(revoked) == 1


@pytest.mark.parametrize('minutes', [1, 4 + 59/60])
def test_shared_writer_blocks_arrival_before_database_access(minutes):
    assert auto.save_violation(None, work_date=datetime.now().date(), employee='Test', reason_item={'name': auto.ARRIVAL_BAND_REASONS[0]}, detail='', source='test', minutes=minutes) == (True, 'SKIP_GRACE_PERIOD')
