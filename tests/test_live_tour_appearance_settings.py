from datetime import datetime
from zoneinfo import ZoneInfo

import vera_web_v2_live_tour as live

NOW = datetime(2026, 9, 17, 10, 0, tzinfo=ZoneInfo('Asia/Ho_Chi_Minh'))


def test_appearance_settings_are_persistent_and_projected():
    state = live._empty_state(NOW)
    payload = {
        'desktop': {'room': {'height': 104, 'width': 150}, 'room_text': {}, 'columns': []},
        'mobile': {'room': {'height': 96, 'width': 92}, 'room_text': {}, 'columns': []},
    }
    result = live._apply_action(state, 'appearance_settings_update', payload, 'admin', NOW)
    assert result['appearance_settings']['desktop']['room']['height'] == 104
    projected = live._state_response(state, 3, NOW)
    assert projected['appearance_settings'] == payload
    assert live._required_action_feature('appearance_settings_update') == 'live_tour_admin'
    assert 'appearance_settings_update' in live.IDEMPOTENCY_REQUIRED_ACTIONS


def test_appearance_settings_reject_unknown_top_level_device():
    state = live._empty_state(NOW)
    try:
        live._apply_action(state, 'appearance_settings_update', {'tablet': {}}, 'admin', NOW)
    except Exception as exc:
        assert getattr(exc, 'status_code', None) == 400
    else:
        raise AssertionError('Expected invalid appearance settings to fail')
