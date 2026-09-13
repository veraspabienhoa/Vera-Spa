from datetime import date
import pytest
from fastapi import HTTPException
from vera_partial_leave_hours import DEFAULT_HOURS, LATE_REASONS, EARLY_REASONS, clock_for, daily_clock
from vera_web_v2_live_tour_payment import default_settings, settings_update


def test_all_requested_reasons_and_four_independent_clocks():
    assert len(LATE_REASONS) == 7
    assert len(EARLY_REASONS) == 8
    for kind in ('late', 'early'):
        assert clock_for('Ca 1', kind) == '15:00'
        assert clock_for('Ca 2', kind) == '17:00'
    assert clock_for('Ca 1', 'late', {'late1': '14:30'}) == '14:30'
    assert clock_for('', 'late') is None


def test_current_week_rotation_controls_clock():
    class Rows:
        def mappings(self): return self
        def all(self): return [{'username': 'an', 'full_name': 'An', 'work_shift': 'Ca 1', 'rotation_cycle': '7 ngày', 'shift_start_date': '2026-09-07', 'partial_leave_times': DEFAULT_HOURS}]
    class Connection:
        def execute(self, *_): return Rows()
    assert daily_clock(Connection(), date(2026, 9, 7), 'an', 'late') == '15:00'
    assert daily_clock(Connection(), date(2026, 9, 14), 'an', 'early') == '17:00'


def test_settings_roundtrip_and_reject_invalid_clocks():
    settings = default_settings()
    settings['partial_leave_times'] = {**DEFAULT_HOURS, 'early1': '14:45'}
    saved = settings_update(settings, lambda value, **_: int(value))
    assert saved['partial_leave_times']['early1'] == '14:45'
    for bad in ('24:00', '15:60', '3PM', None):
        with pytest.raises(HTTPException):
            settings_update({**settings, 'partial_leave_times': {**DEFAULT_HOURS, 'late1': bad}}, lambda value, **_: int(value))
