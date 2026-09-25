from datetime import date
from copy import deepcopy
from unittest.mock import patch

import vera_partial_leave_hours as hours
import vera_web_v2_live_tour as live
from test_live_tour_paged_api import sample
from test_live_tour_server_only import SettingsDatabase, app_client


def test_partial_leave_clock_queries_settings_once_without_any_ledger(monkeypatch):
    monkeypatch.setattr(hours.resource_store, 'enabled', lambda: True)
    monkeypatch.setattr(hours.resource_store, 'read', lambda *a, **k: (_ for _ in ()).throw(AssertionError('full ledger read')))
    statements = []
    class Result:
        def mappings(self): return self
        def all(self): return [{'username':'test', 'work_shift':'Ca 1', 'shift_start_date':'2026-09-01',
                                'rotation_cycle':'', 'partial_leave_times':{'late1':'14:25'}}]
    class Conn:
        def execute(self, sql, params):
            statements.append(str(sql))
            return Result()
    assert hours.daily_clock(Conn(), date(2026,9,25), 'test', 'late') == '14:25'
    assert len(statements) == 1
    assert "payload->'payment_settings'->'partial_leave_times'" in statements[0]
    assert 'vera_live_tour_invoice' not in statements[0]
    assert 'idempotency' not in statements[0]


def test_paged_invoice_normalization_never_copies_other_pages(monkeypatch):
    state = sample()
    _, client = app_client(SettingsDatabase(state))
    monkeypatch.setattr(live.resource_store, 'enabled', lambda: True)
    monkeypatch.setattr(live.resource_store, 'read', lambda *a, **k: (deepcopy(state), 7, {}))
    original = live._normalize_state
    sizes = []
    def normalize(raw, now):
        sizes.append(len(raw.get('invoices', [])))
        assert len(raw.get('invoices', [])) <= 10
        return original(raw, now)
    monkeypatch.setattr(live, '_normalize_state', normalize)
    result = client.get('/v2/live-tour/collections/invoices?page_size=10&page=2').json()
    assert result['total'] == 125
    assert len(result['data']['state']['invoices']) == 10
    assert sizes == [10]
