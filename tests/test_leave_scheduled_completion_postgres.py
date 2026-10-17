from datetime import datetime
import json
from sqlalchemy import text
from test_storage_cleanup import database
from vera_leave_scheduled_completion import complete_due, VN
from vera_web_v2_long_leave import LONG_LEAVE_DATASET


def test_scheduled_completion_persists_once_without_reactivating_staff(database):
    with database.begin() as conn:
        conn.execute(text('''CREATE TABLE vera_phase14_record(dataset text,logical_id text PRIMARY KEY,
            record_type text,record_status text,date_from text,date_to text,payload jsonb,
            updated_by text,revision int DEFAULT 1,updated_at timestamptz)'''))
        for key, kind, first, last, status, payload in [
            ('annual', 'Nghỉ Phép năm', '10/10/2026','16/10/2026','Đã duyệt',{}),
            ('future', 'Nghỉ Phép năm', '17/10/2026','18/10/2026','Đã duyệt',{}),
            ('resign', 'Nghỉ việc', '17/10/2026','17/10/2026','Đã duyệt',{}),
            ('pending', 'Nghỉ Phép năm', '10/10/2026','16/10/2026','Chờ duyệt',{}),
            ('manual', 'Nghỉ Phép năm', '10/10/2026','16/10/2026','Đã duyệt',{'Trạng thái kỳ nghỉ':'Đã kết thúc','Nguồn kết thúc kỳ nghỉ':'manual'}),
        ]:
            conn.execute(text('''INSERT INTO vera_phase14_record(dataset,logical_id,record_type,record_status,date_from,date_to,payload)
                VALUES(:dataset,:key,:kind,:status,:first,:last,CAST(:payload AS jsonb))'''),
                dict(dataset=LONG_LEAVE_DATASET,key=key,kind=kind,status=status,first=first,last=last,payload=json.dumps(payload)))
        now = datetime(2026,10,17,tzinfo=VN)
        assert complete_due(conn, now) == 2
        assert complete_due(conn, now) == 0
    with database.connect() as conn:
        rows = {r['logical_id']: dict(r) for r in conn.execute(text('SELECT * FROM vera_phase14_record')).mappings()}
        assert rows['annual']['revision'] == rows['resign']['revision'] == 2
        assert rows['future']['revision'] == rows['pending']['revision'] == rows['manual']['revision'] == 1
        assert 'Ngày quay lại làm việc' not in rows['resign']['payload']
        assert conn.execute(text('SELECT username FROM employees')).scalar_one() == 'admin'
