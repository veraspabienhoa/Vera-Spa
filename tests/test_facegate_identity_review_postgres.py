from datetime import date
import json

from sqlalchemy import text

from test_facegate_attendance_postgres import database
from test_facegate_identity_review import event, MAPPING
import vera_facegate_identity_review as review
import vera_facegate_sync as sync
import vera_facegate_attendance as fg
import vera_facegate_runtime as runtime


def test_review_uses_readonly_caller_connection_and_preserves_archive(database):
    day = date(2026, 9, 29)
    with database.begin() as conn:
        conn.execute(text('DELETE FROM employees'))
        conn.execute(text("""INSERT INTO employees(username,full_name,role)
            VALUES ('Gia Anh','Nguyễn Gia Anh','letan')"""))
        for key, value in [
            ('registry', {'devices': [{'id': 'facegate-current', 'address': review.ADDRESS}]}),
            ('mapping_synthetic-device', [MAPPING]),
        ]:
            conn.execute(text('UPDATE vera_app_setting SET value_json=CAST(:value AS jsonb) WHERE setting_key=:key'),
                         {'key': key, 'value': json.dumps(value)})
        conn.execute(text("""INSERT INTO vera_work_schedule VALUES
            (:day,'Gia Anh','Nguyễn Gia Anh','letan','Ca 2','17:00','22:00')"""), {'day': day})
        sync.persist_batch(conn, 'synthetic-device', day.isoformat(), [{**event(), 'work_date': day.isoformat()}])
    # Fixture pool size is one: nested acquisitions fail. PostgreSQL rejects any
    # write in this transaction, including accidental archive/mapping updates.
    with database.begin() as conn:
        conn.execute(text('SET TRANSACTION READ ONLY'))
        before = [tuple(r) for r in conn.execute(text('SELECT * FROM vera_facegate_event'))]
        settings = [tuple(r) for r in conn.execute(text('SELECT * FROM vera_app_setting ORDER BY category,setting_key'))]
        data = fg.project_evidence(conn, day, day)
        assert not data['issues']
        assert data['identity_reviews'][0]['id'] == review.REVIEW_ID
        assert json.loads(data['events'][0]['payload_json'])['registration_ref'] is None
        rows = runtime.records(conn, day, day)
        assert len(rows) == 1 and rows[0]['employee_name'] == 'Gia Anh'
        assert rows[0]['check_in'] == '16:31:37' and rows[0]['check_out'] == ''
        assert rows[0]['attendance_pending'] and not rows[0]['attendance_evidence_issues']
        assert rows[0]['applied_identity_review_ids'] == [review.REVIEW_ID]
        assert [tuple(r) for r in conn.execute(text('SELECT * FROM vera_facegate_event'))] == before
        assert [tuple(r) for r in conn.execute(text('SELECT * FROM vera_app_setting ORDER BY category,setting_key'))] == settings
