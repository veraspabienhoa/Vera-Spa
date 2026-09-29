from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from sqlalchemy import text
from fastapi import HTTPException
import vera_online_booking as booking
from test_live_tour_resource_postgres import database
from test_online_booking import payload, client, signature, SECRET


def test_durable_dedup_and_conflicting_replay(database):
    original = booking.WebsiteRequest(**payload())
    with database.begin() as conn: booking.ensure_schema(conn)
    def send(_):
        with database.begin() as conn: return booking.ingest(conn, original)
    with ThreadPoolExecutor(max_workers=3) as pool: results = list(pool.map(send, range(3)))
    assert len({r['id'] for r in results}) == 1
    assert sum(not r['duplicate'] for r in results) == 1
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn: booking.ingest(conn, original.model_copy(update={'guests':3}))
    assert exc.value.status_code == 409
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_online_booking')).scalar_one() == 1


def test_real_receive_pagination_ack_and_revision(database, monkeypatch):
    monkeypatch.setenv('VERA_WEBSITE_WEBHOOK_SECRET', SECRET)
    api = client(engine=database)
    body = json.dumps(payload()).encode()
    received = api.post('/v2/integrations/website/requests', content=body, headers=signature(body))
    assert received.status_code == 200
    booking_id = received.json()['id']
    assert api.post('/v2/integrations/website/requests', content=body, headers=signature(body)).json()['duplicate']
    with database.begin() as conn:
        for _ in range(26): booking.ingest(conn, booking.WebsiteRequest(**payload()))
    first = api.get('/v2/online-bookings').json()
    second = api.get('/v2/online-bookings?page=2').json()
    assert first['total'] == 27 and len(first['rows']) == 25 and len(second['rows']) == 2
    assert not ({r['id'] for r in first['rows']} & {r['id'] for r in second['rows']})
    assert len(api.get('/v2/online-bookings/unread').json()['rows']) == 20
    assert api.post(f'/v2/online-bookings/{booking_id}/seen').status_code == 200
    assert booking_id not in {r['id'] for r in api.get('/v2/online-bookings/unread').json()['rows']}
    assert api.patch(f'/v2/online-bookings/{booking_id}', json={'status':'confirmed','note':'Đã gọi', 'revision':0}).status_code == 200
    assert api.patch(f'/v2/online-bookings/{booking_id}', json={'status':'cancelled','revision':0}).status_code == 409
    confirmed = api.get('/v2/online-bookings?status=confirmed').json()
    assert confirmed['total'] == 1 and confirmed['rows'][0]['note'] == 'Đã gọi'
    assert api.get('/v2/online-bookings?kind=contact').json()['total'] == 0
