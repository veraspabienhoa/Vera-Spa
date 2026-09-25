from vera_vps_runtime_diagnostics import safe_log_summary


def test_log_summary_retains_stack_and_pool_failure_without_private_values():
    message = '''Traceback (most recent call last):
  File "/opt/private-location/vera_web_v2_live_tour.py", line 520, in read_state
    cursor.execute(sql, {"password": "must-not-appear", "customer": "private-name"})
sqlalchemy.exc.TimeoutError: QueuePool limit of size 2 overflow 0 reached, connection timed out, timeout 30.00
[SQL: SELECT * FROM employees WHERE username='private-name']
[parameters: {'token': 'private-token'}]
psycopg.OperationalError: connection to postgresql://secret-user:secret-pass@private-host refused
'''
    assert safe_log_summary(message) == [
        'frame=vera_web_v2_live_tour.py:520:read_state',
        'exception=sqlalchemy.exc.TimeoutError',
        'pool_exhausted size=2 overflow=0 timeout=30.00',
        'exception=psycopg.OperationalError',
    ]


def test_arbitrary_log_bodies_are_not_echoed():
    assert safe_log_summary('Authorization: Bearer private-token\nCustomer: private-name') == []


def test_live_tour_timings_export_only_known_actions_and_numeric_phases():
    message = ("LIVE_TOUR_TIMING action=booking outcome=ok total_ms=5012.34 sql_count=12 sql_ms=4222.10 "
               "phases_ms={'authorize': 12.0, 'write': 4000.0, 'customer': 'private-name'} token=private-token")
    assert safe_log_summary(message) == [
        'live_tour_timing action=booking outcome=ok total_ms=5012.34 sql_count=12 sql_ms=4222.10 authorize_ms=12.0 write_ms=4000.0']
    assert safe_log_summary(message.replace('action=booking', 'action=private-name')) == []


def test_auth_single_line_failure_keeps_safe_cause_only():
    message = 'Web V2 local auth: identity lookup unavailable: OperationalError; cause=OperationalError; sqlstate=08006; pool=private-values'
    assert safe_log_summary(message) == ['auth_lookup_error type=OperationalError cause=OperationalError sqlstate=08006']
    assert safe_log_summary('Web V2 local auth: identity lookup unavailable: private/value; cause=x; sqlstate=oops') == []


def test_activity_query_returns_only_categories_and_ages_with_bound():
    from vera_vps_runtime_diagnostics import ACTIVITY_DETAIL_SQL
    selection = ACTIVITY_DETAIL_SQL.split('FROM pg_stat_activity')[0]
    assert 'LIMIT 20' in ACTIVITY_DETAIL_SQL
    assert 'usename=current_user' in ACTIVITY_DETAIL_SQL
    assert 'same_client_as_diagnostic' in selection
    for unsafe in ['query AS', 'application_name AS', 'client_addr AS', 'usename AS']:
        assert unsafe not in selection
    for field in ['statement_kind', 'transaction_seconds', 'state_seconds', 'query_seconds', 'operation']:
        assert f'AS {field}' in selection
