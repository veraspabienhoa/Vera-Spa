"""The registration boundary must reject HC targets even for Admin."""
import ast
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]


class ReachedCatalog(Exception):
    pass


@pytest.mark.parametrize('filename', ['vera_web_v2_api.py', 'vera_web_v2_api_shared.py'])
@pytest.mark.parametrize('employee_role', ['locker', 'letan', 'tapvu', 'quanly', 'support', 'admin', 'giamdoc', '', 'leader', 'nhanvien'])
def test_registered_target_is_checked_before_catalog_or_writes(filename, employee_role):
    tree = ast.parse((ROOT / filename).read_text())
    fn = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == '_validate_and_prepare')
    calls = []
    class Connection:
        def execute(self, sql, params):
            calls.append((str(sql), params))
            return self
        def mappings(self): return self
        def first(self): return {'username': 'target', 'role': employee_role}
    def catalog(*args): raise ReachedCatalog()
    scope = dict(text=text, HTTPException=HTTPException, LeaveCreate=object, Identity=object,
                 norm=lambda s:s.lower(), _norm=lambda s:s.lower(), _reason_item=catalog)
    exec(compile(ast.Module(body=[fn], type_ignores=[]), filename, 'exec'), scope)
    body = SimpleNamespace(employee_name='target', leave_reason='Reason')
    ident = SimpleNamespace(role='admin', employee_username='operator')
    if employee_role in {'leader', 'nhanvien'}:
        with pytest.raises(ReachedCatalog): scope['_validate_and_prepare'](Connection(), body, ident)
    else:
        with pytest.raises(HTTPException) as error: scope['_validate_and_prepare'](Connection(), body, ident)
        assert error.value.status_code == 400
        assert 'Leader' in error.value.detail
    assert len(calls) == 1
    assert 'SELECT username, role,' in calls[0][0]


def test_manual_recovery_endpoints_and_helpers_are_removed():
    api = (ROOT / 'vera_web_v2_live_tour.py').read_text()
    queue = (ROOT / 'vera_postgres_job_queue.py').read_text()
    assert '/v2/live-tour/recovery' not in api
    assert 'def recover_expired(' not in queue
    assert 'def recovery_history(' not in queue
    assert 'vera_background_job_recovery' not in queue
    # Background work still retains bounded claiming, retries and lease fencing.
    assert 'FOR UPDATE SKIP LOCKED' in queue
    assert 'def mark_retry(' in queue
    assert "status='processing' AND locked_at=:locked_at" in queue


@pytest.mark.parametrize('filename,function', [
    ('vera_web_v2_api.py','leave_records'),
    ('vera_web_v2_api.py','export_leave_excel'),
    ('vera_web_v2_api.py','leave_summary'),
    ('vera_web_v2_api_shared.py','_live_leave_df'),
    ('vera_web_v2_leave_day_stats.py','leave_daily_person_stats'),
    ('vera_web_v2_leave_day_stats.py','leave_list_day_stats'),
])
def test_leave_queries_hide_hc_records_without_deleting_their_financial_source(filename,function):
    import sqlite3
    tree=ast.parse((ROOT/filename).read_text())
    fn=next(n for n in ast.walk(tree) if isinstance(n,ast.FunctionDef) and n.name==function)
    query=next(n.value for n in ast.walk(fn)
               if isinstance(n,ast.Constant) and isinstance(n.value,str)
               and 'FROM leave_records' in n.value
               and ('ORDER BY' in n.value or function=='leave_summary'))
    with sqlite3.connect(':memory:') as conn:
        conn.create_function('btrim',1,lambda value:value.strip() if value is not None else None)
        conn.executescript('''CREATE TABLE employees(username TEXT,role TEXT);
            CREATE TABLE leave_records(id INTEGER,record_uid TEXT,leave_date TEXT,weekday_label TEXT,
              employee_name TEXT,leave_reason TEXT,leave_type TEXT,detail TEXT,penalty REAL,updated_by TEXT,
              updated_at TEXT,created_at TEXT,calculated_days REAL,accumulated_leave REAL,
              update_date TEXT,update_time TEXT);''')
        roles=['leader','nhanvien','locker','letan','tapvu','quanly','support','admin','giamdoc']
        conn.executemany('INSERT INTO employees VALUES(?,?)',[(role,role) for role in roles])
        conn.executemany('INSERT INTO leave_records(id,record_uid,leave_date,employee_name,penalty,leave_type) VALUES(?,?,?,?,?,?)',
                         [(i,role,'2026-10-07',role,50000,'Không phép') for i,role in enumerate(roles)])
        conn.row_factory=sqlite3.Row
        rows=conn.execute(query,dict(start_date='2026-10-01',end_date='2026-10-31',d='2026-10-07',uid='')).fetchall()
        assert {row['employee_name'] for row in rows}=={'leader','nhanvien'}
        assert conn.execute('SELECT COUNT(*) FROM leave_records').fetchone()[0]==len(roles)
        assert conn.execute("SELECT penalty FROM leave_records WHERE employee_name='locker'").fetchone()[0]==50000


def test_month_query_applies_the_same_ktv_scope():
    import sqlite3
    from vera_web_v2_leave_month import MONTH_ROWS
    with sqlite3.connect(':memory:') as conn:
        conn.create_function('btrim',1,lambda value:value.strip() if value else value)
        conn.executescript("""CREATE TABLE employees(username TEXT,role TEXT);
            CREATE TABLE leave_records(record_uid TEXT,leave_date TEXT,weekday_label TEXT,
              employee_name TEXT,leave_reason TEXT,leave_type TEXT,detail TEXT,penalty REAL,
              updated_by TEXT,updated_at TEXT);
            INSERT INTO employees VALUES('KTV','nhanvien'),('HC','locker');
            INSERT INTO leave_records(record_uid,leave_date,employee_name,penalty)
              VALUES('ktv','2026-10-07','KTV',10000),('hc','2026-10-07','HC',50000);""")
        conn.row_factory=sqlite3.Row
        rows=conn.execute(str(MONTH_ROWS),dict(start='2026-10-01',stop='2026-11-01')).fetchall()
        assert [row['record_uid'] for row in rows]==['ktv']
        assert conn.execute('SELECT COUNT(*) FROM leave_records').fetchone()[0]==2
