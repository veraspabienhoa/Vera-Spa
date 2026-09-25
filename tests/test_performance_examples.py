from concurrent.futures import ThreadPoolExecutor
from threading import Event
from datetime import date
import pytest
from vera_read_cache import ReadCache
from examples.performance.month_api import month_bounds, MONTH_ROWS
from examples.performance.invoice_policy import invoice_policy
from vera_technical_retention import PRUNE


def test_month_window_never_reads_previous_month_and_handles_leap_year():
    assert month_bounds('2024-02') == (date(2024,2,1), date(2024,3,1))
    assert month_bounds('2026-12') == (date(2026,12,1), date(2027,1,1))
    for bad in ['2026-00','2026-13','09-2026','2026-1',None]:
        with pytest.raises(ValueError): month_bounds(bad)
    assert 'leave_date >= :start AND leave_date < :stop' in str(MONTH_ROWS)


def test_cache_is_detached_bounded_and_invalidated_after_commit():
    cache=ReadCache(max_entries=1)
    value=cache.get_or_load('a',lambda:{'rows':[1]})
    value['rows'].append(2)
    assert cache.get_or_load('a',lambda:None)=={'rows':[1]}
    cache.get_or_load('b',lambda:[3])
    assert len(cache._entries)==1
    cache.invalidate()
    assert cache.get_or_load('a',lambda:[4])==[4]


def test_inflight_cache_cannot_repopulate_after_invalidation():
    cache=ReadCache(); entered=Event(); release=Event()
    def old():
        entered.set(); assert release.wait(2); return 'old'
    with ThreadPoolExecutor(2) as pool:
        old_result=pool.submit(cache.get_or_load,'k',old)
        assert entered.wait(2)
        cache.invalidate()
        assert cache.get_or_load('k',lambda:'new')=='new'
        release.set()
        assert old_result.result()=='old'
    assert cache.get_or_load('k',lambda:'wrong')=='new'


def test_retail_allows_same_content_but_all_requests_protect_replay():
    retail=invoice_policy([{'price':100}])
    combo=invoice_policy([{'price':100},{'combo_purchase_id':'p'}])
    assert not retail.content_duplicate_check
    assert retail.request_replay_protection and combo.request_replay_protection
    assert not retail.protect_combo_consumption and combo.protect_combo_consumption


def test_retention_is_limited_to_completed_technical_jobs():
    sql=str(PRUNE)
    assert "status='done'" in sql and 'make_interval(days=>:days)' in sql
    assert 'FOR UPDATE SKIP LOCKED' in sql and 'LIMIT :batch' in sql
    assert all(name not in sql for name in ('vera_live_tour_invoice','vera_live_tour_meta','leave_records'))


def test_month_api_reads_only_requested_month_and_rechecks_permissions():
    from types import SimpleNamespace
    from fastapi import FastAPI, HTTPException
    from fastapi.testclient import TestClient
    from sqlalchemy import create_engine, text
    from sqlalchemy.pool import StaticPool
    from examples.performance.month_api import install_month_api
    engine=create_engine('sqlite://',poolclass=StaticPool,connect_args={'check_same_thread':False})
    with engine.begin() as conn:
        conn.execute(text('CREATE TABLE leave_records(record_uid text,leave_date date,weekday_label text,employee_name text,leave_reason text,leave_type text,detail text,penalty int,updated_by text,updated_at text)'))
        for uid,day in [('before','2026-08-31'),('inside','2026-09-25'),('after','2026-10-01')]:
            conn.execute(text('INSERT INTO leave_records(record_uid,leave_date,employee_name,penalty) VALUES(:uid,:day,\'Test\',100)'),locals())
    ident=SimpleNamespace(employee_username='test',role='letan')
    allowed=[True]
    def require(conn, who, feature):
        if not allowed[0]: raise HTTPException(403)
    app=FastAPI()
    invalidate=install_month_api(app,engine_instance=lambda:engine,current_identity=lambda:ident,
        require_feature=require,feature_allowed=lambda *a:False)
    with TestClient(app) as client:
        data=client.get('/v2/leave/month-records?month=2026-09').json()
        assert [row['record_uid'] for row in data['records']]==['inside']
        assert 'penalty' not in data['records'][0]
        with engine.begin() as conn:
            conn.execute(text("UPDATE leave_records SET detail='saved' WHERE record_uid='inside'"))
        invalidate()
        assert client.get('/v2/leave/month-records?month=2026-09').json()['records'][0]['detail']=='saved'
        allowed[0]=False
        assert client.get('/v2/leave/month-records?month=2026-09').status_code==403
    engine.dispose()


def test_cache_serializes_postgres_numeric_like_fastapi():
    from decimal import Decimal
    cache=ReadCache()
    assert cache.get_or_load('penalty',lambda:{'penalty':Decimal('100000.00'),'part':Decimal('0.5')})=={'penalty':100000,'part':0.5}
