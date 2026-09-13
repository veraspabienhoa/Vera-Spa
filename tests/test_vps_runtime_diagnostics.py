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
