from types import SimpleNamespace

import vera_live_tour_queue_alerts as alerts


def test_evaluate_queue_alert_thresholds_are_strict():
    healthy = {
        'last_success_age': 600,
        'oldest_pending': 600,
        'retry': 3,
        'failed': 0,
        'stale_processing': 0,
    }
    assert alerts.evaluate(healthy) == []

    unhealthy = {
        'last_success_age': 600.1,
        'oldest_pending': 601,
        'retry': 1,
        'failed': 2,
        'stale_processing': 1,
    }
    assert alerts.evaluate(unhealthy) == [
        'last_success_age', 'oldest_pending', 'failed', 'stale_processing'
    ]


def test_payload_contains_actionable_queue_context():
    metrics = {
        'last_success_age': 720,
        'oldest_pending': 660,
        'retry': 2,
        'failed': 1,
        'stale_processing': 1,
    }
    payload = alerts._payload('alert', metrics, alerts.evaluate(metrics))
    assert payload['kind'] == 'live-tour-queue-alert'
    assert payload['url'] == 'https://app.veraspa.vn/'
    assert '12.0 phút' in payload['body']
    assert '11.0 phút' in payload['body']
    assert 'failed=1' in payload['body']
    assert 'processing quá lease=1' in payload['body']


def test_monitor_once_only_delivers_when_event_is_claimed(monkeypatch):
    metrics = {
        'last_success_age': 700,
        'oldest_pending': None,
        'retry': 0,
        'failed': 0,
        'stale_processing': 0,
    }
    monkeypatch.setattr(alerts, '_claim_event', lambda *args: (None, {}))
    called = []
    monkeypatch.setattr(alerts, '_deliver', lambda *args: called.append('deliver'))
    result = alerts.monitor_once(lambda: None, 'live_tour_projection', metrics)
    assert result == {'event': 'none', 'conditions': ['last_success_age'], 'sent': 0}
    assert called == []


def test_monitor_once_records_delivery(monkeypatch):
    metrics = {
        'last_success_age': 700,
        'oldest_pending': None,
        'retry': 0,
        'failed': 0,
        'stale_processing': 0,
    }
    monkeypatch.setattr(alerts, '_claim_event', lambda *args: ('alert', {}))
    monkeypatch.setattr(alerts, '_deliver', lambda *args: (2, ''))
    recorded = []
    monkeypatch.setattr(
        alerts,
        '_record_delivery',
        lambda *args: recorded.append(SimpleNamespace(event=args[2], sent=args[3], error=args[4])),
    )
    result = alerts.monitor_once(lambda: None, 'live_tour_projection', metrics)
    assert result['event'] == 'alert'
    assert result['sent'] == 2
    assert recorded[0].event == 'alert'
    assert recorded[0].sent == 2
