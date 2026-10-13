"""Isolated outbox integration; no real device or production account."""
from sqlalchemy import text
from test_notification_schema_locking import database
from test_unified_notifications_postgres import notices, subscribe, dispatch
from test_notification_routing import Identity
from vera_live_tour_early_completion import enqueue_early_completions


def test_early_completion_exact_audience_channels_retry_and_rollback(database, notices):
    accounts, identity, client = notices
    result = {'pending': {'entries': [{'employee_id':'e1','employee_name':'nhanvien','service':'Body 90','room':'1.1',
        'started_at':'2026-10-13T10:00:00+07:00','completed_at':'2026-10-13T11:25:00+07:00',
        'completion_delta_minutes':-5,'started_by':'letan','completed_by':'admin'}]}}
    with database.begin() as conn:
        enqueue_early_completions(conn,result)
        enqueue_early_completions(conn,result)
    with database.connect() as conn:
        rows=list(conn.execute(text('SELECT recipient,channel FROM vera_notification_delivery')).mappings())
    audience={'admin','quanly','letan','nhanvien'}
    assert len(rows)==12
    assert {row['recipient'] for row in rows} == {accounts[role] for role in audience}
    assert {row['channel'] for row in rows} == {'in_app','popup','push'}
    for role, account in accounts.items():
        identity[0]=Identity(role=role,auth_user_id=account)
        response=client.get('/v2/notification-inbox')
        assert response.status_code==200
        assert len(response.json()['notifications']) == (1 if role in audience else 0)
    for role in audience:
        subscribe(database,accounts[role])
    assert len(dispatch(database))==4
    assert dispatch(database)==[]
    # A business rollback rolls the enqueued notice back too.
    conn=database.connect(); transaction=conn.begin()
    result['pending']['entries'][0]['completed_at']='2026-10-13T11:20:00+07:00'
    enqueue_early_completions(conn,result)
    transaction.rollback();conn.close()
    with database.connect() as conn:
        assert conn.execute(text('SELECT COUNT(*) FROM vera_notification_delivery')).scalar()==12
