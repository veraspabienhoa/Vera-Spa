import json
from datetime import date
from unittest.mock import patch

from sqlalchemy import create_engine, text

import vera_facegate_sync as sync
from vera_web_v2_devices import filtered_records, history_workbook, saved_facegate_history


def test_saved_history_matches_confirmed_reference_without_device_io():
    engine = create_engine('sqlite://')
    ref = {'file_type': 0, 'file_index': 2, 'file_position': 77}
    day = '2026-09-24'
    with engine.begin() as conn:
        sync.ensure_schema(conn)
        conn.execute(text('CREATE TABLE vera_app_setting(category text, setting_key text, value_json text)'))
        conn.execute(text('INSERT INTO vera_app_setting VALUES (:category,:key,:value)'), {
            'category': 'facegate', 'key': 'mapping_2023044',
            'value': json.dumps([{'registration_ref': ref, 'confirmed_by': 'admin',
                                  'username': 'Test Employee', 'employee_code': 'TEST01'}])})
        events = [dict(event_id=1, occurred_at=day+'T08:00:00+07:00', device_name='Test Employee',
                       status_code='1', type_code='0', registration_ref=ref),
                  dict(event_id=2, occurred_at=day+'T09:00:00+07:00', device_name='Khác',
                       status_code='1', type_code='0', registration_ref=None)]
        sync.persist_batch(conn, '2023044', day, sync.prepare_batch({
            'source': 'facegate_control_log', 'total_count': 2, 'truncated': False,
            'records': events}, day))
    with patch.dict('os.environ', {'VERA_FACEGATE_DEVICE_ID': '2023044'}), engine.connect() as conn:
        data = saved_facegate_history(conn, date.fromisoformat(day), date.fromisoformat(day))
    assert [item['mapping_status'] for item in data['records']] == ['reference_match', 'unmapped']
    assert data['records'][0]['employee_code'] == 'TEST01'
    assert len(filtered_records(data['records'], 'facegate_saved', employee='TEST01')) == 1
    payload = {**data, 'source': 'facegate_saved', 'start': day, 'end': day,
               'filters': {'employee': '', 'event_id': '', 'event_date': '', 'status': '', 'event_type': ''}}
    assert history_workbook(payload).startswith(b'PK')
    engine.dispose()
