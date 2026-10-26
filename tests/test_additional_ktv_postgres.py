from copy import deepcopy

import vera_live_tour_resource_store as store
import vera_web_v2_live_tour as live
from test_live_tour_additional_ktv import setup_booking
from test_live_tour_backend import NOW
from test_live_tour_resource_postgres import database


def test_pair_commits_under_both_employee_locks_and_rejects_stale_revision(database):
    fixture, payload = setup_booking()
    with database.begin() as conn:
        store.lock(conn)
        before, _, _ = store.read(conn)
        updated = deepcopy(before)
        updated['services'] = fixture['services']
        revision = store.write(conn, before, updated, 'admin')
    with database.begin() as conn:
        before, _, fresh = store.begin_action(
            conn, 'booking', payload, revision, 'paired-booking-test', live._counter_business_date(NOW).isoformat())
        assert fresh
        working = deepcopy(before)
        live._apply_action(working, 'booking', payload, 'admin', NOW)
        store.write(conn, before, working, 'admin')
    with database.begin() as conn:
        persisted, _, _ = store.read(conn)
        main, extra = persisted['employees']
        assert main['additional_ktv_id'] == extra['id']
        assert extra['duration'] == main['duration'] == 90
        assert extra['service_price'] == 100000
    with database.begin() as conn:
        _, _, fresh = store.begin_action(
            conn, 'booking', payload, revision, 'stale-paired-booking',
            live._counter_business_date(NOW).isoformat())
        assert not fresh  # The HTTP action handler translates this into 409.
