"""Website boundary tests: no production traffic or customer data."""
import hashlib
import hmac
import json
import time
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import ValidationError
import vera_online_booking as booking

SECRET = 'test-only-' + 'x' * 40


def payload(**overrides):
    return dict(event_id=str(uuid4()), kind='booking', customer_name='Khách kiểm thử',
                phone='0900000000', appointment_date='2026-09-30', appointment_time='14:30',
                service='VIP 90 phút', guests=2, **overrides)


def signature(body, timestamp=None):
    timestamp = str(int(time.time())) if timestamp is None else timestamp
    return {'X-Vera-Timestamp': timestamp, 'X-Vera-Signature': hmac.new(SECRET.encode(), timestamp.encode()+b'.'+body, hashlib.sha256).hexdigest()}


def test_signature_tamper_expiry_and_unconfigured_fail_closed():
    body = b'{"example":1}'
    headers = signature(body)
    booking.verify_signature(body, headers['X-Vera-Timestamp'], headers['X-Vera-Signature'], SECRET)
    for candidate, stamp, sig, key in [
        (body+b' ', headers['X-Vera-Timestamp'], headers['X-Vera-Signature'], SECRET),
        (body, '1000000000', headers['X-Vera-Signature'], SECRET),
        (body, None, None, SECRET), (body, headers['X-Vera-Timestamp'], 'wrong', SECRET),
        (body, headers['X-Vera-Timestamp'], headers['X-Vera-Signature'], ''),
    ]:
        with pytest.raises(HTTPException):
            booking.verify_signature(candidate, stamp, sig, key)


def test_validation_and_contact_missing_appointment():
    assert booking.WebsiteRequest(**payload()).guests == 2
    contact = booking.WebsiteRequest(event_id=uuid4(), kind='contact', customer_name='Test', phone='0900000000', message='Xin tư vấn')
    assert contact.appointment_date is None and contact.guests is None
    for changes in ({'appointment_date': '2026-02-30'}, {'appointment_time':'24:00'}, {'guests':0}, {'guests':True}, {'service':''}, {'phone':'<script>123'}, {'customer_name':'  '}):
        data = payload(); data.update(changes)
        with pytest.raises(ValidationError): booking.WebsiteRequest(**data)


def client(role='admin', engine=None, locked=False):
    app = FastAPI()
    ident = SimpleNamespace(role=role, must_change_password=locked, auth_user_id='test-user', employee_username='test')
    def forbidden_engine(): raise AssertionError('Unauthorized request accessed business DB')
    booking.install_online_booking_routes(app, engine_instance=(lambda: engine) if engine else forbidden_engine, current_identity=lambda: ident)
    return TestClient(app)


@pytest.mark.parametrize('role,locked', [('nhanvien',False), ('leader',False), ('admin',True)])
@pytest.mark.parametrize('method,path,body', [
    ('GET','/v2/online-bookings',None), ('GET','/v2/online-bookings/unread',None),
    ('POST','/v2/online-bookings/1/seen',None), ('PATCH','/v2/online-bookings/1', {'status':'handled','revision':0}),
])
def test_all_inbox_routes_deny_unauthorized_before_database(role, locked, method, path, body):
    response = client(role, locked=locked).request(method,path,json=body)
    assert response.status_code == 403


def test_webhook_rejects_unsigned_oversized_and_invalid_without_db(monkeypatch):
    monkeypatch.setenv('VERA_WEBSITE_WEBHOOK_SECRET', SECRET)
    api = client()
    assert api.post('/v2/integrations/website/requests', json=payload()).status_code == 401
    assert api.post('/v2/integrations/website/requests', content=b'x' * (booking.MAX_BODY+1)).status_code == 413
    body = b'{"customer_name":"private-value"}'
    response = api.post('/v2/integrations/website/requests', content=body, headers=signature(body))
    assert response.status_code == 422 and 'private-value' not in response.text


def test_listing_rejects_invalid_calendar_and_reversed_range_before_database():
    api = client()
    assert api.get('/v2/online-bookings?date_from=2026-02-30').status_code == 422
    assert api.get('/v2/online-bookings?date_from=2026-10-02&date_to=2026-10-01').status_code == 422
