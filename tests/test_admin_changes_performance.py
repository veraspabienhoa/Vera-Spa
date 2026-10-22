from datetime import date
from types import SimpleNamespace
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
import vera_web_v2_operations_v41 as mod

class Result:
    def __init__(self, rows): self.rows = rows
    def mappings(self): return self
    def scalars(self): return self
    def all(self): return self.rows

class Conn:
    def __init__(self): self.calls = []
    def __enter__(self): return self
    def __exit__(self, *args): pass
    def execute(self, stmt, params=None):
        sql = str(stmt); self.calls.append((sql, params))
        assert 'DELETE ' not in sql
        if 'DISTINCT actor' in sql: return Result(['Nguyễn Ánh', 'Bình'])
        return Result([])


def test_indexed_vietnam_boundaries_and_actor_before_limit():
    conn = Conn()
    mod._audit_rows(conn, date(2026,10,1), date(2026,10,31), 'anh', limit=101, offset=100)
    sql, p = conn.calls[-1]
    assert 'AT TIME ZONE' not in sql and '::date' not in sql
    assert p['start_at'].isoformat() == '2026-10-01T00:00:00+07:00'
    assert p['end_at'].isoformat() == '2026-11-01T00:00:00+07:00'
    assert p['actors'] == ['Nguyễn Ánh']
    assert 'actor IN' in sql and 'expires_at >= NOW()' in sql
    assert p['limit'] == 101 and p['offset'] == 100


def make_client(monkeypatch, role='admin', rows=101):
    conn = Conn()
    engine = SimpleNamespace(connect=lambda: conn)
    app = FastAPI()
    calls = []
    def read(c, start, end, actor, **kw):
        calls.append(kw)
        return [dict(id=i,event_type='insert') for i in range(rows)]
    monkeypatch.setattr(mod, '_audit_rows', read)
    mod.install_operations_v41(app,engine_instance=lambda:engine,
        current_identity=lambda:SimpleNamespace(role=role),require_feature=lambda *a:None,identity_type=SimpleNamespace)
    return TestClient(app), calls, conn


def test_page_is_bounded_read_only_and_has_more(monkeypatch):
    c,calls,conn = make_client(monkeypatch)
    r=c.get('/v2/admin/changes-v41?start=2026-10-01&end=2026-10-31&page=2&archive_page=3')
    assert r.status_code==200,r.text
    data=r.json()
    assert len(data['changes'])==len(data['archive'])==100
    assert data['has_more'] and data['archive_has_more']
    assert calls[0]['offset']==100 and calls[1]['offset']==200
    assert calls[0]['limit']==calls[1]['limit']==101
    assert not conn.calls


def test_permission_denied_before_read(monkeypatch):
    c,calls,_=make_client(monkeypatch,role='letan')
    assert c.get('/v2/admin/changes-v41?start=2026-10-01&end=2026-10-31').status_code==403
    assert not calls


def test_export_never_silently_truncates(monkeypatch):
    c,_,_=make_client(monkeypatch,rows=5001)
    assert c.get('/v2/admin/changes-v41/export.xlsx?start=2026-10-01&end=2026-10-31').status_code==400


def test_postgres_read_only_boundaries_paging_and_expiry():
    import os
    from uuid import uuid4
    from sqlalchemy import create_engine, text
    url=os.getenv('VERA_TEST_POSTGRES_URL')
    if not url: pytest.skip('Real PostgreSQL runs in CI')
    engine=create_engine(url)
    schema='audit_read_'+uuid4().hex
    try:
        with engine.begin() as conn:
            conn.execute(text(f'CREATE SCHEMA {schema}'))
            conn.execute(text(f'SET LOCAL search_path TO {schema}'))
            conn.execute(text('''CREATE TABLE vera_v2_leave_change_detail (
                id bigserial primary key,event_type text,record_uid text,employee_name text,
                leave_date text,actor text,source text,old_data jsonb,new_data jsonb,
                created_at timestamptz,expires_at timestamptz)'''))
            conn.execute(text('CREATE INDEX audit_created ON vera_v2_leave_change_detail(created_at DESC)'))
            conn.execute(text("""INSERT INTO vera_v2_leave_change_detail(event_type,actor,created_at,expires_at)
                SELECT 'update','Nguyễn Ánh', '2026-10-21T17:00:00Z'::timestamptz, NOW()+INTERVAL '1 day'
                FROM generate_series(1,205)"""))
            conn.execute(text("""INSERT INTO vera_v2_leave_change_detail(event_type,actor,created_at,expires_at) VALUES
                ('insert','Bình','2026-10-21T16:59:59Z',NOW()+INTERVAL '1 day'),
                ('insert','Bình','2026-10-22T17:00:00Z',NOW()+INTERVAL '1 day'),
                ('update','Nguyễn Ánh','2026-10-22T10:00:00Z',NOW()-INTERVAL '1 day')"""))
        with engine.begin() as conn:
            conn.execute(text('SET TRANSACTION READ ONLY'))
            conn.execute(text(f'SET LOCAL search_path TO {schema}'))
            first=mod._audit_rows(conn,date(2026,10,22),date(2026,10,22),'anh',limit=101)
            second=mod._audit_rows(conn,date(2026,10,22),date(2026,10,22),'anh',limit=101,offset=100)
            assert len(first)==len(second)==101
            assert first[100]['id']==second[0]['id']
            assert len(mod._audit_rows(conn,date(2026,10,22),date(2026,10,22),''))==205
            assert len(mod._audit_rows(conn,date(2026,10,22),date(2026,10,22),'',archive_only=True))==205
    finally:
        with engine.begin() as conn:conn.execute(text(f'DROP SCHEMA IF EXISTS {schema} CASCADE'))
        engine.dispose()
