"""Fresh popup decisions are independent of invoice sync / notification delivery."""
import json
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from sqlalchemy import text, event

import vera_missing_checkin_notifications as alerts
from test_notification_schema_locking import database


def test_current_absence_uses_fresh_cache_roster_and_one_caller_connection(database, monkeypatch):
    monkeypatch.setenv('VERA_LIVE_TOUR_RESOURCE_MODE', 'off')
    monkeypatch.setattr(alerts, '_manual_shift_overrides', lambda conn, day: {})
    now = datetime(2026, 9, 27, 16, 30, tzinfo=timezone(timedelta(hours=7)))
    definitions = [{'Tên ca': 'Ca 1', 'Ca chính': 'Ca 1', 'Giờ bắt đầu': '10:00'},
                   {'Tên ca': 'Ca 2', 'Ca chính': 'Ca 2', 'Giờ bắt đầu': '13:00'}]
    base = [{'EmployeeName':'Other', 'WorkDateStr':'27/09/2026', 'MachineTimeCheckInStr':'27/09/2026 10:00:00'}]
    with database.begin() as conn:
        conn.execute(text('''CREATE TABLE vera_dataset_cache(dataset_key text, payload jsonb, source_version text, updated_at timestamptz, expires_at timestamptz);
            CREATE TABLE employees(username text,full_name text,role text,payload jsonb,work_shift text,rotation_cycle text,shift_start_date text);
            CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb);
            CREATE TABLE vera_work_schedule(employee_username text,employee_name text,department text,shift_code text,start_time text,work_date date);
            CREATE TABLE vera_work_shift_definition(department text,shift_code text,start_time text);
            CREATE TABLE leave_records(employee_name text,leave_date date,source_sheet_id text);'''))
        conn.execute(text("INSERT INTO vera_app_setting VALUES ('shift','shift_definitions',CAST(:defs AS jsonb))"),{'defs':json.dumps(definitions)})
        conn.execute(text("INSERT INTO employees VALUES ('Test Employee','Test Employee Full Name','nhanvien','{}','Ca 1','Theo chu kỳ Tuần','2026-08-17')"))
        conn.execute(text("INSERT INTO vera_dataset_cache VALUES ('timesoft_employee_checkin_today',CAST(:payload AS jsonb),'2026-09-27',:now,:expires)"),
                     {'payload':json.dumps(base),'now':now,'expires':now+timedelta(minutes=30)})
    queries = []
    def sql_listener(conn,cursor,statement,parameters,context,executemany): queries.append(statement)
    event.listen(database, 'before_cursor_execute', sql_listener)
    with database.begin() as conn:
        def no_checkout(*args): raise AssertionError('must not acquire another connection')
        event.listen(database, 'checkout', no_checkout)
        try:
            def read(role='admin', clock=now, username='', full_name=''):
                return alerts.current_missing_checkins(conn,SimpleNamespace(role=role, employee_username=username, full_name=full_name),clock,include_expiry=True)
            rows=read()
            assert len(rows)==1 and rows[0]['employee']=='Test Employee'
            assert 'Ca 2 lúc 13:00' in rows[0]['body']
            assert rows[0]['expires_at']=='2026-09-27T16:40:00+07:00'
            assert len(queries)==4 and all(sql.lstrip().startswith('SELECT') for sql in queries)
            assert read('letan')==rows and read('quanly')==rows
            assert read('nhanvien')==[]
            assert read('nhanvien', username='Test Employee')==rows
            assert read('nhanvien', username=' test employee ')==rows
            assert read('nhanvien', username='other', full_name='Test Employee Full Name')==[]
            assert read('nhanvien', username='Test Employeé')==[]
            assert read('giamdoc', username='Test Employee')==[]
            # Audience policy uses the current account role, not schedule labels.
            for role in ('leader','letan','locker','tapvu','support','quanly','giamdoc'):
                conn.execute(text("INSERT INTO employees VALUES (:name,:name,:role,'{}','Ca 1','','2026-08-17')"),
                             {'name':f'Test {role}','role':role})
                conn.execute(text("INSERT INTO vera_work_schedule VALUES (:name,:name,'nhanvien','Ca 1','10:00','2026-09-27')"),
                             {'name':f'Test {role}'})
            assert {r['employee'] for r in read('letan')} == {'Test Employee','Test leader','Test letan'}
            expected = {'Test Employee','Test leader','Test letan','Test locker','Test tapvu','Test support'}
            assert {r['employee'] for r in read('admin')} == expected
            assert {r['employee'] for r in read('quanly')} == expected
            for role in ('leader','locker','tapvu','support'):
                assert [r['employee'] for r in read(role, username=f'Test {role}')] == [f'Test {role}']
            assert read('nhanvien', username='Test Employee')==rows
            conn.execute(text("UPDATE employees SET role='quanly' WHERE username='Test letan'"))
            assert 'Test letan' not in {r['employee'] for r in read('letan')}
            conn.execute(text("DELETE FROM vera_work_schedule"))
            conn.execute(text("DELETE FROM employees WHERE username <> 'Test Employee'"))
            assert read(clock=now+timedelta(minutes=11))==[]
            assert read(clock=now-timedelta(seconds=1))==[]
            assert read(clock=now+timedelta(days=1))==[]
            def payload(rows):
                conn.execute(text('UPDATE vera_dataset_cache SET payload=CAST(:value AS jsonb)'),{'value':json.dumps(rows)})
            for scan in [
                {'MachineTimeStr':'27/09/2026 00:30:00'},
                {'MachineTimeCheckOutStr':'27/09/2026 14:00:00'},
                {'MachineTimeCheckInStr':'26/09/2026 13:00:00'},
                {'MachineTimeCheckInStr':'27/09/2026 17:00:00'},
            ]:
                payload(base+[{'EmployeeName':'Test Employee',**scan}]); assert len(read())==1
            payload(base+[{'EmployeeName':'Test Employee Full Name','MachineTimeCheckInStr':'27/09/2026 13:00:00'}]);assert read()==[]
            assert read('nhanvien', username='Test Employee')==[]
            payload([]);assert read()==[]
            payload(base)
            conn.execute(text("INSERT INTO leave_records VALUES ('Test Employee','2026-09-27','postgres:auto_check')"));assert len(read())==1
            conn.execute(text("INSERT INTO leave_records VALUES ('Test Employee','2026-09-27','manual')"));assert read()==[]
            assert read('nhanvien', username='Test Employee')==[]
            conn.execute(text('DELETE FROM leave_records'))
            conn.execute(text("INSERT INTO vera_work_schedule VALUES ('Test Employee','Test Employee','nhanvien','Nghỉ','','2026-09-27')"));assert read()==[]
        finally:
            event.remove(database,'checkout',no_checkout)
    event.remove(database,'before_cursor_execute',sql_listener)
