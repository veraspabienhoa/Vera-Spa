from datetime import datetime, timedelta

import pytest
import vera_web_v2_live_tour as live
from test_live_tour_backend import state_with, employee


@pytest.mark.parametrize('clock,expected', [
    ('00:00:00', '2026-09-13T00:00:00'),
    ('00:00:01', '2026-09-12T23:59:00'),
    ('00:15:00', '2026-09-12T23:59:00'),
    ('01:00:00', '2026-09-12T23:59:00'),
    ('01:00:01', '2026-09-13T01:00:01'),
])
def test_booking_time_boundaries(clock, expected):
    instant = datetime.fromisoformat('2026-09-13T' + clock + '+07:00')
    assert live._adjust_booking_time(instant).isoformat() == expected + '+07:00'


def test_quick_booking_current_day_normalizes_without_manual_backdate_reason():
    now = datetime(2026, 9, 13, 0, 30, tzinfo=live.VN_TZ)
    assert live._quick_booking_at({'booked_at': '2026-09-13T00:20:00+07:00'}, now).isoformat() == '2026-09-12T23:59:00+07:00'


def test_automatic_leave_day_rolls_at_five(monkeypatch):
    from test_live_tour_server_only import SettingsDatabase
    queried = []
    class Database(SettingsDatabase):
        def execute(self, statement, params=None):
            if 'FROM leave_records' in str(statement):
                queried.append(params['day'])
            return super().execute(statement, params)
    db = Database(state_with())
    live._read_state(db, datetime(2026, 9, 13, 4, 59, 59, tzinfo=live.VN_TZ))
    live._read_state(db, datetime(2026, 9, 13, 5, 0, tzinfo=live.VN_TZ))
    assert [day.isoformat() for day in queried] == ['2026-09-12', '2026-09-13']


def test_midnight_start_orders_waiting_bookings_once_and_excludes_new_bookings():
    now = datetime(2026, 9, 13, 0, 15, tzinfo=live.VN_TZ)
    state = state_with(employee('e1', 'An'), employee('e2', 'Bình'), employee('e3', 'Cúc'))
    for index, row in enumerate(state['employees']):
        row.update(work_status='Đi làm', shift='Ca 1', service='Body 90', room=f'1.{index + 1}',
                   status='Đang chờ', duration=90, booked_at=(now - timedelta(minutes=5 * index)).isoformat())
    state['employees'][0]['booked_at'] = (now + timedelta(seconds=1)).isoformat()
    live._auto_start_waiting(state, now - timedelta(seconds=1))
    assert all(row['status'] == 'Đang chờ' for row in state['employees'])
    live._auto_start_waiting(state, now)
    assert state['employees'][0]['status'] == 'Đang chờ'
    assert state['employees'][2]['started_at'] == now.isoformat()
    assert state['employees'][1]['started_at'] == (now + timedelta(seconds=1)).isoformat()
    counts = [row['tour_count'] for row in state['employees']]
    live._auto_start_waiting(state, now + timedelta(minutes=1))
    assert [row['tour_count'] for row in state['employees']] == counts
