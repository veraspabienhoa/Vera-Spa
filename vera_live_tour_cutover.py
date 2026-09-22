"""Offline cutover/rollback. Stop ALL API and projection writers before running.

No environment flags are changed here. The operator selects the serving mode
only after this transaction commits and verification succeeds.
"""
import argparse
import json
from copy import deepcopy
from uuid import uuid4
from sqlalchemy import text
import vera_live_tour_relational as store
import vera_live_tour_resource_store as resources
from vera_vps_concurrency_schema import _runtime_engine


def run(conn, rollback=False):
    conn.execute(text("SET LOCAL lock_timeout='5s'"))
    conn.execute(text('SELECT pg_advisory_xact_lock(hashtext(:key))'), {'key':'vera:v2:live_tour:state'})
    resources.lock(conn)
    if rollback:
        state, revision, _ = resources.read(conn)
        state.pop('_resource_ready', None)
        conn.execute(text("UPDATE vera_app_setting SET value_json=CAST(:state AS jsonb),revision=:revision,updated_at=NOW() WHERE category='live_tour' AND setting_key='state'"), {'state':store._json(state),'revision':revision})
        meta, _ = store._split(state)
        conn.execute(text(f"UPDATE {store.META_TABLE} SET payload=CAST(:payload AS jsonb),payload_hash=:hash WHERE singleton=1"), {'payload':store._json(meta),'hash':store._digest(meta)})
        return {'ok':True,'revision':revision,'mode':'aggregate'}
    store.ensure_schema(conn)
    row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='live_tour' AND setting_key='state' FOR UPDATE")).mappings().first()
    if not row:
        raise RuntimeError('Board must be initialized before cutover')
    existing, _ = store.load_state(conn)
    if (existing or {}).get('_resource_ready'):
        raise RuntimeError('Already activated; refuse to overwrite canonical resource rows')
    store.sync_changes(conn, existing, row['value_json'], row['revision'], force=True)
    if not store.parity(conn,row['value_json'],row['revision'])['ok']:
        raise RuntimeError('Cutover parity failed')
    canonical = deepcopy(row['value_json'])
    for collection in store.RESOURCE_COLLECTIONS:
        for item in canonical.get(collection, []):
            item.setdefault('id', str(uuid4()))
    store.sync_changes(conn, row['value_json'], canonical, row['revision'], force=True)
    conn.execute(text(f"UPDATE {store.META_TABLE} SET payload=payload || '{{\"_resource_ready\":true}}'::jsonb WHERE singleton=1"))
    return {'ok':True,'revision':row['revision'],'mode':'resources'}


if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--writers-stopped',action='store_true',required=True)
    parser.add_argument('--rollback',action='store_true')
    args=parser.parse_args()
    try:
        with _runtime_engine().begin() as conn:
            result=run(conn,args.rollback)
        print(json.dumps(result))
    except Exception as exc:
        raise SystemExit(f'Live Tour cutover rolled back: {type(exc).__name__}') from None
