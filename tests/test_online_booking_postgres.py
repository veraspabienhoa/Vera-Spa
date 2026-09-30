from concurrent.futures import ThreadPoolExecutor
import json
import pytest
from sqlalchemy import text
from fastapi import HTTPException
import vera_online_booking as booking
from test_live_tour_resource_postgres import database
from test_online_booking import payload, client, signature, SECRET


def test_durable_dedup_and_conflicting_replay(database):
    original = booking.WebsiteRequest(**payload(phone='', service='', requested_staff='AN AN'))
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
        row = conn.execute(text('SELECT phone,service,requested_staff FROM vera_online_booking')).mappings().one()
        assert row == {'phone': '', 'service': '', 'requested_staff': 'AN AN'}


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


def test_receive_calls_staff_appointment_writer_only_for_today(database, monkeypatch):
    from datetime import datetime, timedelta
    from zoneinfo import ZoneInfo
    monkeypatch.setenv('VERA_WEBSITE_WEBHOOK_SECRET', SECRET)
    today = datetime.now(ZoneInfo('Asia/Ho_Chi_Minh')).date()
    calls = []
    api = client(engine=database, appointment_writer=lambda *args: calls.append(args) or {'applied': True})
    same_day = payload(appointment_date=today.isoformat(), requested_staff='AN AN')
    body = json.dumps(same_day).encode()
    response = api.post('/v2/integrations/website/requests', content=body, headers=signature(body))
    assert response.status_code == 200 and response.json()['staff_appointment']['applied'] is True
    assert calls == [('AN AN', today, same_day['appointment_time'])]

    next_day = payload(appointment_date=(today + timedelta(days=1)).isoformat(), requested_staff='AN AN')
    body = json.dumps(next_day).encode()
    response = api.post('/v2/integrations/website/requests', content=body, headers=signature(body))
    assert response.status_code == 200 and 'staff_appointment' not in response.json()
    assert len(calls) == 1


def test_listing_filters_dates_before_pagination_and_uses_vietnam_contact_day(database):
    with database.begin() as conn:
        booking.ensure_schema(conn)
        for day in ('2026-09-30', '2026-10-01'):
            for _ in range(26):
                data = payload(); data['appointment_date'] = day
                booking.ingest(conn, booking.WebsiteRequest(**data))
        contact = booking.WebsiteRequest(event_id=__import__('uuid').uuid4(), kind='contact', customer_name='Test', phone='0900000000', message='Test')
        saved = booking.ingest(conn, contact)
        conn.execute(text("UPDATE vera_online_booking SET created_at='2026-09-30T18:00:00Z' WHERE id=:id"), {'id':saved['id']})
    api = client(engine=database)
    first = api.get('/v2/online-bookings?date_from=2026-10-01&date_to=2026-10-01').json()
    second = api.get('/v2/online-bookings?date_from=2026-10-01&date_to=2026-10-01&page=2').json()
    assert first['total'] == 27 and len(first['rows']) == 25 and len(second['rows']) == 2
    assert all(row['appointment_date'] in ('2026-10-01', None) for row in first['rows'] + second['rows'])


def test_upcoming_includes_recent_past_and_excludes_old_and_closed_before_pagination(database):
    from datetime import timedelta
    with database.begin() as conn:
        booking.ensure_schema(conn)
        now = conn.execute(text("SELECT CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'")).scalar_one()
        future = (now + timedelta(days=1)).date().isoformat()
        past = (now - timedelta(days=1)).date().isoformat()
        expected = []
        earlier = now - timedelta(minutes=119)
        data = payload(); data.update(appointment_date=earlier.date().isoformat(), appointment_time=earlier.strftime('%H:%M'))
        expected.append(booking.ingest(conn, booking.WebsiteRequest(**data))['id'])
        too_old = now - timedelta(minutes=121)
        data = payload(); data.update(appointment_date=too_old.date().isoformat(), appointment_time=too_old.strftime('%H:%M'))
        booking.ingest(conn, booking.WebsiteRequest(**data))
        for index in range(30):
            data = payload(); data.update(appointment_date=future, appointment_time='10:00')
            saved = booking.ingest(conn, booking.WebsiteRequest(**data))
            expected.append(saved['id'])
        for day, status in [(past, 'new'), (future, 'cancelled'), (future, 'handled')]:
            data = payload(); data.update(appointment_date=day)
            saved = booking.ingest(conn, booking.WebsiteRequest(**data))
            conn.execute(text('UPDATE vera_online_booking SET status=:status WHERE id=:id'), dict(status=status, id=saved['id']))
    api = client(engine=database)
    first = api.get('/v2/online-bookings?upcoming=true').json()
    second = api.get('/v2/online-bookings?upcoming=true&page=2').json()
    assert first['total'] == 31
    assert [row['id'] for row in first['rows'] + second['rows']] == expected
    assert api.patch(f"/v2/online-bookings/{expected[0]}", json={'status':'handled','revision':0}).status_code == 200
    assert api.get('/v2/online-bookings?upcoming=true').json()['total'] == 30


@pytest.mark.parametrize('role', ['admin', 'quanly', 'letan'])
def test_manual_booking_is_durable_and_retry_does_not_duplicate(database, role):
    api = client(role=role, engine=database)
    data = payload()
    first = api.post('/v2/online-bookings', json=data)
    assert first.status_code == 200
    replay = api.post('/v2/online-bookings', json=data)
    assert replay.status_code == 200 and replay.json()['duplicate']
    assert replay.json()['id'] == first.json()['id']
    rows = api.get('/v2/online-bookings').json()['rows']
    assert len(rows) == 1 and rows[0]['updated_by'] == 'test'
    assert rows[0]['customer_name'] == data['customer_name']
    assert rows[0]['status'] == 'new'
    assert api.post('/v2/online-bookings', json={**data, 'guests':3}).status_code == 409
    assert api.post('/v2/online-bookings', json={**data, 'kind':'contact'}).status_code == 422


@pytest.mark.parametrize('minutes,status,expected', [(-121,'new',0),(-120,'new',1),(-119,'confirmed',1),
    (0,'new',1),(120,'confirmed',1),(14400,'new',1),(0,'handled',0),(0,'cancelled',0)])
def test_booking_window_exact_boundary_crosses_vietnam_midnight(database, minutes, status, expected):
    from datetime import datetime, timedelta
    now = datetime(2026,10,1,0,30)
    appointment = now + timedelta(minutes=minutes)
    predicate = booking.UPCOMING_WINDOW_SQL.replace("CURRENT_TIMESTAMP AT TIME ZONE 'Asia/Ho_Chi_Minh'", "CAST(:now AS timestamp)")
    with database.begin() as conn:
        count = conn.execute(text("""WITH b AS (SELECT 'booking' AS kind, CAST(:status AS text) AS status,
            CAST(:day AS date) AS appointment_date, CAST(:time AS text) AS appointment_time)
            SELECT count(*) FROM b WHERE """ + predicate), dict(now=now, status=status,
            day=appointment.date(), time=appointment.strftime('%H:%M'))).scalar_one()
        assert count == expected
