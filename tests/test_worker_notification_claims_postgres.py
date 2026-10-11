"""A dead notification worker cannot release or overwrite a recovered claim."""
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from sqlalchemy import text
import vera_notification_delivery as delivery
from test_unified_notifications_postgres import database, notices, subscribe


def seed(database, accounts):
    subscribe(database, accounts['admin'])
    with database.begin() as conn:
        assert delivery.enqueue(conn, 'admin_leave_changes', {'title':'Synthetic', 'tag':'claim-test'})


def test_two_dispatchers_send_one_committed_notification(database, notices):
    accounts, _, _ = notices
    seed(database, accounts)
    barrier = Barrier(2)
    def dispatch():
        sent = []
        barrier.wait()
        delivery.dispatch_pending(database, lambda *_: (sent.append(1) or True, 201, ''), lambda *_: 'test')
        return len(sent)
    with ThreadPoolExecutor(max_workers=2) as executor:
        counts = list(executor.map(lambda _: dispatch(), range(2)))
    assert sum(counts) == 1


def test_stale_completion_cannot_clear_recovered_claim_or_overwrite_progress(database, notices):
    accounts, _, _ = notices
    seed(database, accounts)
    new_owner = {}
    def send(item, *_):
        assert database.pool.checkedout() == 0
        with database.begin() as conn:
            row = conn.execute(text("""UPDATE vera_notification_delivery
                SET claimed_at=clock_timestamp(),sent_subscriptions='["new-owner"]'::jsonb
                WHERE id=:id RETURNING id,claimed_at"""),
                {'id': int(item['payload']['notification_id'])}).mappings().one()
            new_owner.update(row)
        return True, 201, ''
    delivery.dispatch_pending(database, send, lambda *_: 'test')
    with database.connect() as conn:
        row = conn.execute(text('SELECT * FROM vera_notification_delivery WHERE id=:id'), new_owner).mappings().one()
        assert row['claimed_at'] == new_owner['claimed_at']
        assert row['sent_at'] is None
        assert row['sent_subscriptions'] == ['new-owner']
    stale = {**new_owner, 'claimed_at': None}
    assert delivery._refresh_claim(database, stale) is False
