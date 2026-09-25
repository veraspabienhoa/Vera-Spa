from copy import deepcopy

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW


def test_full_audit_history_uses_bounded_database_round_trips():
    before = live._empty_state(NOW)
    before['audit'] = [{'id': f'event-{i:04}', 'action': 'test', 'detail': {}}
                       for i in range(live.MAX_AUDIT)]
    after = deepcopy(before)
    live._audit(after, 'test', {}, 'test', NOW)
    calls = []
    class Result:
        def scalar_one(self): return 8
    class Conn:
        info = {'live_tour_exclusive': True}
        def execute(self, statement, parameters):
            calls.append((str(statement), parameters))
            return Result()
    store.write(Conn(), before, after, 'test')
    assert len(after['audit']) == live.MAX_AUDIT
    assert len(calls) <= 6, f'audit eviction made {len(calls)} database round trips'
