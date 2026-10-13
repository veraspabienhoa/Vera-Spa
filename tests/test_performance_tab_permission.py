from datetime import timedelta

from test_live_tour_backend import NOW, employee, state_with
from test_live_tour_invoice_permissions import scoped_client
from vera_web_v2_permissions import DEFAULT_ROLE_FEATURES


def test_performance_requires_explicit_grant_for_non_admin():
    assert all('live_tour_performance_view' not in features for role, features in DEFAULT_ROLE_FEATURES.items() if role != 'admin')


def test_performance_report_granted_account_read_and_revocation(monkeypatch):
    worker = employee('e1', 'An')
    worker.update(service='Body 90', room='1.1', duration=90, started_at=NOW.isoformat(), completed_at=(NOW+timedelta(minutes=80)).isoformat())
    state = state_with(worker)
    grants = {'live_tour_reports_view', 'live_tour_performance_view', 'live_tour_export'}
    client, _ = scoped_client(monkeypatch, state, grants)
    response = client.get('/v2/live-tour/reports', params={'tab': 'performance', 'preset': 'all'})
    assert response.status_code == 200, response.text
    assert len(response.json()['rows']) == 1
    assert response.json()['capabilities']['performance_view'] is True
    assert client.get('/v2/live-tour/export.xlsx', params={'kind': 'performance', 'preset': 'all'}).status_code == 200
    grants.remove('live_tour_performance_view')
    assert client.get('/v2/live-tour/reports', params={'tab': 'performance'}).status_code == 403
    assert client.get('/v2/live-tour/export.xlsx', params={'kind': 'performance'}).status_code == 403
    assert client.get('/v2/live-tour/reports').json()['performance'] == []
    assert client.get('/v2/live-tour/reports', params={'tab': 'revenue'}).status_code == 200
