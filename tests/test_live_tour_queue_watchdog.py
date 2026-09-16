import vera_live_tour_queue_watchdog as watchdog


def test_watchdog_thresholds_and_unreachable_health():
    assert watchdog.evaluate_health_payload({
        'last_success_age': 600,
        'oldest_pending': 600,
        'retry': 5,
        'failed': 0,
        'stale_processing': 0,
    }) == []
    assert watchdog.evaluate_health_payload({
        'last_success_age': 600.1,
        'oldest_pending': 601,
        'retry': 0,
        'failed': 2,
        'stale_processing': 1,
    }) == ['last_success_age', 'oldest_pending', 'failed', 'stale_processing']
    assert watchdog.evaluate_health_payload({'watchdog_error': 'API unavailable'}) == ['health_unreachable']


def test_issue_body_is_actionable_and_contains_no_alerting_error_blob():
    payload = {
        'counts': {'done': 42},
        'last_success_age': 720,
        'oldest_pending': 660,
        'retry': 1,
        'failed': 1,
        'stale_processing': 0,
        'alerting': {'channel': {'error': 'private implementation detail'}},
    }
    body = watchdog.issue_body(
        payload,
        ['last_success_age', 'oldest_pending', 'failed'],
        'https://github.com/example/repo/actions/runs/1',
    )
    assert '720.0s' in body
    assert '660.0s' in body
    assert 'failed: `1`' in body
    assert 'Watchdog run:' in body
    assert 'private implementation detail' not in body


def test_sync_issue_opens_once_and_closes_on_recovery(monkeypatch):
    calls = []
    open_issue = {'number': 12, 'title': watchdog.ISSUE_TITLE}

    monkeypatch.setattr(watchdog, '_find_open_issue', lambda repo, token: None)
    monkeypatch.setattr(
        watchdog,
        '_github_request',
        lambda token, method, url, payload=None: calls.append((method, url, payload)) or {},
    )
    action = watchdog.sync_issue(
        repo='owner/repo', token='token',
        payload={'last_success_age': 700}, conditions=['last_success_age'], run_url='',
    )
    assert action == 'opened'
    assert calls[-1][0] == 'POST'
    assert calls[-1][1].endswith('/issues')

    calls.clear()
    monkeypatch.setattr(watchdog, '_find_open_issue', lambda repo, token: open_issue)
    action = watchdog.sync_issue(
        repo='owner/repo', token='token',
        payload={'last_success_age': 10, 'retry': 0, 'failed': 0, 'stale_processing': 0},
        conditions=[], run_url='',
    )
    assert action == 'recovered'
    assert calls[0][1].endswith('/issues/12/comments')
    assert calls[1][2] == {'state': 'closed', 'state_reason': 'completed'}
