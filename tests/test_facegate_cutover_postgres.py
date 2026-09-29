from datetime import timedelta
import json
import pytest
from sqlalchemy import text

from test_facegate_attendance_postgres import database, seed_preview, DAY
import vera_web_v2_attendance_query_perf as attendance
import vera_facegate_attendance as fg
from vera_web_v2_live_tour_checkin import with_checkin
from vera_facegate_control_log import VN_TZ
from datetime import datetime


def test_official_reader_and_live_tour_use_facegate_without_modifying_history(database, monkeypatch, tmp_path):
    seed_preview(database)
    path = tmp_path/'source.json'
    path.write_text(json.dumps({'version': 1, 'source': 'facegate', 'effective_date': DAY.isoformat()}))
    monkeypatch.setenv('VERA_ATTENDANCE_SOURCE_FILE', str(path))
    import requests
    monkeypatch.setattr(requests.sessions.Session, 'request', lambda *_a, **_k: pytest.fail('Network during attendance read'))
    with database.begin() as conn:
        projection = fg.project_evidence(conn, DAY, DAY)
        conn.execute(text('INSERT INTO vera_dataset_cache VALUES (:key, CAST(:rows AS jsonb))'),
                     {'key': f'facegate_employee_checkin_{DAY:%Y%m%d}', 'rows': json.dumps(projection['rows'])})
    with database.connect() as conn:
        before = list(conn.execute(text('SELECT * FROM vera_dataset_cache ORDER BY dataset_key')))
        rows = attendance._records_v42_fast(conn, DAY, DAY)
        assert rows[0]['check_in'] == '09:59:00'
        assert rows[0]['evidence_source'] == 'facegate'
        assert rows[0]['attendance_preview'] is False
        assert rows[0]['attendance_pending'] is True  # no checkout invented
        historical = fg.preview(conn, DAY, DAY)
        assert historical['evidence_differences'] == []
        directory = attendance._active_roster(conn)
        checked = with_checkin(conn, directory, datetime.combine(DAY, datetime.min.time()).replace(hour=12, tzinfo=VN_TZ))
        assert checked[0]['daily_shift']
        assert list(conn.execute(text('SELECT * FROM vera_dataset_cache ORDER BY dataset_key'))) == before
