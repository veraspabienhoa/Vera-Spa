"""Transactional online-booking notifications and delivery to the four allowed roles."""
from uuid import uuid4
import pytest
from sqlalchemy import text
import vera_online_booking as booking
from test_online_booking import payload, client
from test_notification_schema_locking import database
from test_unified_notifications_postgres import notices, subscribe, dispatch


def prepare(database, notices):
    accounts, _, _ = notices
    accounts = dict(accounts, locker=str(uuid4()))
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_v2_user_profile VALUES(CAST(:id AS uuid),'Locker','locker',true)"), {'id': accounts['locker']})
        booking.ensure_schema(conn)
    return accounts


def test_new_booking_queues_exact_roles_once_and_dispatches_after_commit(database, notices):
    accounts = prepare(database, notices)
    data = booking.WebsiteRequest(**payload())
    with database.begin() as conn:
        result = booking.ingest(conn, data)
    with database.begin() as conn:
        assert booking.ingest(conn, data)['duplicate']
        rows = conn.execute(text('SELECT recipient,channel FROM vera_notification_delivery')).mappings().all()
    wanted = {accounts[r] for r in ('admin','letan','quanly','locker')}
    assert {(r['recipient'], r['channel']) for r in rows} == {(r, c) for r in wanted for c in ('in_app','push')}
    assert len(rows) == 8
    for role in ('admin','letan','quanly','locker','nhanvien'):
        subscribe(database, accounts[role])
    sent = dispatch(database)
    assert {p['recipient_id'] for p in sent} == wanted
    assert all('30-09-2026' in p['body'] for p in sent)
    assert dispatch(database) == []
    # Reading/acknowledging does not grant Locker mutation rights.
    api = client('locker', engine=database)
    assert api.get('/v2/online-bookings/unread').json()['rows'][0]['id'] == result['id']
    assert api.post(f"/v2/online-bookings/{result['id']}/seen").status_code == 200
    assert api.get('/v2/online-bookings/unread').json()['rows'] == []
    assert api.patch(f"/v2/online-bookings/{result['id']}", json={'status':'handled','revision':0}).status_code == 403


def test_booking_rollback_also_rolls_back_notifications(database, notices):
    prepare(database, notices)
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            booking.ingest(conn, booking.WebsiteRequest(**payload()))
            raise RuntimeError('rollback')
    with database.connect() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_online_booking')).scalar() == 0
        assert conn.execute(text('SELECT count(*) FROM vera_notification_delivery')).scalar() == 0


def test_role_revocation_prevents_queued_push_delivery(database, notices):
    accounts = prepare(database, notices)
    subscribe(database, accounts['locker'])
    with database.begin() as conn:
        booking.ingest(conn, booking.WebsiteRequest(**payload()))
        conn.execute(text("UPDATE vera_v2_user_profile SET role='nhanvien' WHERE auth_user_id=CAST(:id AS uuid)"), {'id': accounts['locker']})
    assert dispatch(database) == []
