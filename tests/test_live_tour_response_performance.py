from copy import deepcopy

import pytest
from sqlalchemy import create_engine, text

import vera_web_v2_live_tour as live
from vera_live_tour_timing import ActionTiming
from test_live_tour_backend import NOW, employee


def fixture_state():
    state = live._empty_state(NOW)
    state['rooms'] = [{'id': f'r{i}', 'name': f'{i // 5 + 1}.{i % 5 + 1}',
                       'area_name': f'Phòng {i // 5 + 1}', 'active': i % 13 != 0}
                      for i in range(50)]
    state['employees'] = []
    for i in range(45):
        row = employee(f'e{i+1}', f'Test {i}')
        row.update(room=state['rooms'][i]['name'], service='PR 90' if i % 7 == 0 else 'Body 90',
                   status=['Đang chờ', 'Đang thực hiện', 'CHO THANH TOÁN'][i % 3])
        state['employees'].append(row)
    return state


def test_indexed_projection_preserves_room_occupancy_and_has_no_input_mutation():
    state = fixture_state()
    before = deepcopy(state)
    expected = [r['name'] for r in state['rooms'] if r['active'] and live._room_available(state, r['name'])]
    result = live._board_response(state, 7, NOW, can_operate=True, can_admin=True)
    assert result['available_beds'] == expected
    assert result['room_groups'] == {r['name']: live._catalog_room_group(state, r['name']) for r in state['rooms']}
    assert result['service_areas'] == live._service_areas(state)
    assert result['room_action_counts'] == live._room_action_counts(state)
    assert state == before


def test_room_index_and_private_cache_do_not_survive_a_catalog_change():
    state = fixture_state()
    first = live._ResponseState(state)
    assert live._catalog_room_group(first, '1.1') == 'Phòng 1'
    assert not live._catalog_private_service(first, 'Body 90')
    state['rooms'][0]['area_name'] = 'Khu mới'
    next(r for r in state['services'] if r['name'] == 'Body 90')['private'] = True
    second = live._ResponseState(state)
    assert live._catalog_room_group(second, '1.1') == 'Khu mới'
    assert live._catalog_private_service(second, 'Body 90')


@pytest.mark.parametrize('value', [None, 0, False, 12, ['ĐẶT LỊCH'], ' ĐẶT_LỊCH  ', 'a' * 300])
def test_normalization_keeps_existing_semantics(value):
    assert live._norm(value) == live._normalize_text(str(value or ''))


def test_repeated_board_projection_bounds_unicode_normalization_work(monkeypatch):
    state = fixture_state()
    live._cached_normalize_text.cache_clear()
    calls = 0
    original = live.unicodedata.normalize
    def count(*args):
        nonlocal calls
        calls += 1
        return original(*args)
    monkeypatch.setattr(live.unicodedata, 'normalize', count)
    live._board_response(state, 7, NOW, can_operate=True)
    first = calls
    for _ in range(3):
        live._board_response(state, 7, NOW, can_operate=True)
    assert first < 1000
    assert calls == first
    assert live._cached_normalize_text.cache_info().maxsize == 4096


def test_action_timing_counts_sql_and_does_not_log_values_or_keep_listeners(caplog):
    engine = create_engine('sqlite://')
    trace = ActionTiming('booking')
    trace.started -= 1
    with caplog.at_level('INFO', logger='uvicorn.error'):
        with trace.transaction(engine) as conn:
            conn.execute(text('SELECT :secret'), {'secret': 'PRIVATE_CUSTOMER_VALUE'})
        trace.mark('write')
        trace.emit()
        with engine.begin() as conn:
            conn.execute(text('SELECT 1'))
    assert trace.sql_count == 1
    assert 'sql_count=1' in caplog.text and 'write' in caplog.text
    assert 'PRIVATE_CUSTOMER_VALUE' not in caplog.text and 'SELECT' not in caplog.text
    engine.dispose()
