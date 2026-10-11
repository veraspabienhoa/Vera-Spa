"""Benchmark fixture tests run in a subprocess, isolating its network boundary."""
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def check(code):
    result = subprocess.run([sys.executable, "-c", code], cwd=ROOT, capture_output=True, text=True, timeout=45)
    assert result.returncode == 0, result.stderr


def test_fixture_is_repeatable_and_has_all_payment_scenarios():
    check('''
from scripts.benchmark_checkout_postgres import make_dataset, compact_json
first, bodies = make_dataset(100, 12)
second, again = make_dataset(100, 12)
assert compact_json(first) == compact_json(second)
assert bodies == again
assert len(first['invoices']) == len(first['reports']) == 100
assert len(first['invoice_changes']) == 10
assert {body['scenario'] for body in bodies} == {'auto','manual','pending','combo'}
assert len({body['idempotency_key'] for body in bodies}) == 12
assert len(first['pending']) == 3
''')


def test_nearest_rank_tail_and_empty_metrics():
    check('''
from scripts.benchmark_checkout_postgres import percentiles
assert percentiles([]) == {'n':0,'p50':None,'p95':None}
assert percentiles(range(1,21)) == {'n':20,'p50':10.5,'p95':19}
assert percentiles([9,1]) == {'n':2,'p50':5.0,'p95':9}
''')


def test_external_http_is_blocked_before_proxy_routing():
    check('''
from scripts import benchmark_checkout_postgres
import requests, socket
try:
    requests.get('https://api.vietqr.io/v2/banks', timeout=.1)
except requests.ConnectionError as error:
    assert 'disabled' in str(error)
else:
    raise AssertionError('External HTTP unexpectedly allowed')
try:
    socket.getaddrinfo('api.vietqr.io',443)
except OSError as error:
    assert 'disabled' in str(error)
else:
    raise AssertionError('External DNS unexpectedly allowed')
''')


def test_runner_requires_disposable_database_acknowledgement():
    result = subprocess.run([sys.executable, str(ROOT / 'scripts/benchmark_checkout_postgres.py'),
                             '--output', '/tmp/not-created-checkout-benchmark.json'],
                            cwd=ROOT, capture_output=True, text=True, timeout=45)
    assert result.returncode == 2
    assert '--allow-disposable-local-postgres' in result.stderr
