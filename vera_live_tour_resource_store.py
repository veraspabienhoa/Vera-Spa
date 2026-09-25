"""Authoritative row storage after an explicit, verified offline cutover.

Independent employee, room and invoice operations share a maintenance fence
and lock their business resources.
Cross-resource business operations take the exclusive fence until their complete
read sets have been certified. All writes are row diffs, never aggregate rewrites.
"""
from copy import deepcopy
import json
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import text
import vera_live_tour_relational as relational
import vera_resource_concurrency as concurrency

FENCE = 'vera:live-tour:resource-fence:v1'
INDEPENDENT = frozenset({'start', 'start_room', 'update_appointment', 'set_vip', 'add_minutes', 'booking', 'multi_booking', 'update_booking', 'cancel_booking', 'restart_booking', 'complete', 'set_shift', 'set_work_status', 'start_break', 'end_break', 'replace_service', 'add_service', 'move_pending', 'finish_to_pending', 'checkout', 'quick_checkout', 'pending_update', 'pending_delete', 'paid_invoice_update', 'paid_invoice_delete', 'combo_purchase', 'combo_import'})
FINANCIAL = frozenset({'checkout','quick_checkout','paid_invoice_update','paid_invoice_delete','combo_purchase','combo_import'})
LOCK_DISCOVERY_COLLECTIONS = frozenset({'employees', 'rooms', 'customers', 'pending', 'invoices'})
PAYMENT_ACTIONS = frozenset({'checkout', 'quick_checkout'})
PAYMENT_COLLECTIONS = frozenset({'employees', 'rooms', 'services', 'combos', 'customers', 'pending', 'invoices', 'invoice_changes'})
PAYMENT_APPENDS = frozenset({'invoices', 'reports', 'combo_usage', 'audit'})
OPERATIONAL_ACTIONS = frozenset({'booking', 'multi_booking', 'update_booking', 'cancel_booking', 'restart_booking', 'start', 'start_room', 'finish_room', 'complete', 'finish_to_pending', 'move_pending', 'update_appointment', 'set_vip', 'add_minutes', 'set_shift', 'set_work_status', 'start_break', 'end_break', 'replace_service', 'add_service', 'pending_update', 'pending_delete'})
ADJUSTMENT_ACTIONS = frozenset({'paid_invoice_update', 'paid_invoice_delete'})
OPERATIONAL_COLLECTIONS = frozenset({'employees', 'rooms', 'services', 'combos', 'customers', 'pending', 'break_events', 'combo_sale_requests'})


class _ScopedSnapshot(dict):
    """Certified partial read: omitted history is untouched, new history appends."""
    appends = frozenset()
    writable = frozenset()


class _OperationalSnapshot(_ScopedSnapshot):
    appends = frozenset({'audit', 'pending_changes'})
    writable = frozenset({'employees', 'customers', 'pending', 'break_events'}) | appends


class _AdjustmentSnapshot(_ScopedSnapshot):
    appends = frozenset({'audit', 'invoice_changes'})
    writable = frozenset({'employees', 'customers', 'invoices', 'reports', 'combo_usage'}) | appends


class _PaymentSnapshot(_ScopedSnapshot):
    """Internal checkout read set, never a full board or export snapshot.

    Existing invoices/change history contain numbering headers only, except
    the current replay's canonical invoice. Missing collections are untouched;
    new ledger rows are appended by write() under the publication row lock.
    """
    appends = PAYMENT_APPENDS
    writable = frozenset({'employees', 'customers', 'pending'}) | appends


class _ReceiptSnapshot(dict):
    """Detached persisted JSON receipts with a C-backed independent copy.

    Receipt results are already JSON values read from PostgreSQL. Walking every
    nested value through Python's generic deepcopy dominates mutation/projection
    CPU as this durable history grows. A JSON round trip keeps every receipt and
    nested result independent without sharing mutable data between transactions.
    No bytes from outside this method are deserialized here.
    """

    def __deepcopy__(self, memo):
        copied = type(self)()
        memo[id(self)] = copied
        try:
            copied.update(json.loads(json.dumps(self, ensure_ascii=False)))
        except (TypeError, ValueError):
            # Defensive compatibility for an in-memory, non-JSON result. The
            # PostgreSQL reader itself always supplies JSON-compatible values.
            copied.update(deepcopy(dict(self), memo))
        return copied


def enabled():
    return relational.mode() == 'active'


def lock(conn, *, shared=False):
    conn.info['live_tour_exclusive'] = not shared
    fn = 'pg_try_advisory_xact_lock_shared' if shared else 'pg_try_advisory_xact_lock'
    if not conn.execute(text(f'SELECT {fn}(hashtextextended(:key,0))'), {'key': FENCE}).scalar():
        raise HTTPException(503, 'Tài nguyên đang được cập nhật. Vui lòng thử lại.', headers={'Retry-After': '1'})


def read(conn, collections=None, *, payment_key=None, receipt_key=None, profile=None):
    # One statement = one MVCC snapshot across all collections and the revision.
    params = {}
    arms = []
    snapshot_type = dict
    if profile == 'operational':
        collections = OPERATIONAL_COLLECTIONS
        snapshot_type = _OperationalSnapshot
    elif profile == 'adjustment':
        collections = OPERATIONAL_COLLECTIONS | {'invoices', 'reports', 'combo_usage'}
        snapshot_type = _AdjustmentSnapshot
    elif profile is not None:
        raise ValueError('Unknown Live Tour read profile')
    if payment_key is not None:
        collections = PAYMENT_COLLECTIONS
        params['payment_key'] = payment_key
        receipt_key = payment_key
        snapshot_type = _PaymentSnapshot
    for name, table in relational.RESOURCE_TABLES.items():
        if collections is not None and name not in collections:
            continue
        projection = 'payload'
        if payment_key is not None and name == 'invoices':
            projection = f"""CASE WHEN resource_id=(SELECT payload->'idempotency'->:payment_key->'result'->'invoice'->>'id'
                FROM {relational.META_TABLE} WHERE singleton=1) THEN payload
                ELSE jsonb_build_object('id',resource_id,'bill_no',payload->'bill_no') END"""
        elif payment_key is not None and name == 'invoice_changes':
            projection = "jsonb_build_object('id',resource_id,'before',jsonb_build_object('bill_no',payload->'before'->'bill_no'))"
        arms.append(f"SELECT '{name}' AS kind,resource_id,ordinal,{projection} AS payload,aggregate_revision FROM {table} WHERE deleted_at IS NULL")
    meta_payload = "payload" if collections is None else "payload - 'idempotency'"
    if receipt_key is not None:
        params['receipt_key'] = receipt_key
        meta_payload = """(payload - 'idempotency') || jsonb_build_object('idempotency',
            CASE WHEN (payload->'idempotency') ? :receipt_key
            THEN jsonb_build_object(:receipt_key,payload->'idempotency'->:receipt_key)
            ELSE '{}'::jsonb END)"""
    arms.append(f"SELECT '_meta','',0,{meta_payload},aggregate_revision FROM {relational.META_TABLE} WHERE singleton=1")
    statement = text(' UNION ALL '.join(arms))
    rows = (conn.execute(statement, params) if params else conn.execute(statement)).mappings().all()
    meta = next((row for row in rows if row['kind'] == '_meta'), None)
    if meta is None or not meta['payload'].get('_resource_ready'):
        raise HTTPException(503, 'Chưa hoàn tất chuyển đổi dữ liệu Live Tour.')
    owned_meta = dict(meta['payload'])
    if isinstance(owned_meta.get('idempotency'), dict):
        owned_meta['idempotency'] = _ReceiptSnapshot(owned_meta['idempotency'])
    state = deepcopy(owned_meta)
    state = snapshot_type(state)
    versions = {}
    for kind in relational.RESOURCE_COLLECTIONS:
        state[kind] = []
    for row in sorted((row for row in rows if row['kind'] != '_meta'), key=lambda row: (row['kind'], row['ordinal'], row['resource_id'])):
        value = deepcopy(row['payload'])
        state[row['kind']].append(value)
        versions[(row['kind'], row['resource_id'])] = int(row['aggregate_revision'])
    return state, int(meta['aggregate_revision']), versions


def action_resources(state, action, payload, idempotency_key):
    resources = {('live_tour_idempotency', idempotency_key)}
    ids = {str(value) for value in payload.get('employee_ids', []) if value}
    if payload.get('employee_id'):
        ids.add(str(payload['employee_id']))
    parts = [payload, *payload.get('bookings', []), *([payload['quick_booking']] if isinstance(payload.get('quick_booking'),dict) else [])]
    for part in parts:
        if part.get('employee_id'):
            ids.add(str(part['employee_id']))
    for kind, field in [('pending','pending_id'),('invoices','invoice_id')]:
        if payload.get(field):
            resources.add(('live_tour_' + kind, str(payload[field])))
            record = next((row for row in state[kind] if str(row.get('id')) == str(payload[field])), {})
            parts.append(record)
            parts.extend(record.get('entries', []))
            ids.update(str(row['employee_id']) for row in record.get('entries', []) if row.get('employee_id'))
    if action == 'start_room':
        from vera_web_v2_live_tour import _room_action_members
        ids.update(str(row['id']) for row in _room_action_members(state, str(payload.get('room') or '').strip(), action))
    parts.extend(row for row in state['employees'] if str(row.get('id')) in ids)
    resources.update(('live_tour_employee', value) for value in ids)
    for part in parts:
        room = str(part.get('room') or '')
        room_row = next((row for row in state['rooms'] if row.get('id') == part.get('room_id') or room and row.get('name') == room), None)
        if room_row:
            room = str(room_row.get('name') or room)
        if room:
            # Lock physical room, including all beds and PR occupancy.
            from vera_web_v2_live_tour import _catalog_room_group
            resources.add(('live_tour_room', _catalog_room_group(state, room)))
        customer_id = str(part.get('customer_id') or '')
        phone = str(part.get('customer_phone') or part.get('phone') or '')
        name = str(part.get('customer_name') or '')
        if customer_id:
            resources.add(('live_tour_customer', customer_id))
        if phone:
            resources.add(('live_tour_customer_phone', ''.join(c for c in phone if c.isdigit())))
        if name:
            resources.add(('live_tour_customer_name', name))
        for row in state['customers']:
            if str(row.get('id')) == customer_id or phone and ''.join(c for c in str(row.get('phone') or '') if c.isdigit()) == ''.join(c for c in phone if c.isdigit()) or name and row.get('name') == name:
                resources.add(('live_tour_customer', str(row['id'])))
    if action in FINANCIAL:
        # Invoice numbering and adjustments share a ledger invariant. This does
        # not block bookings or employee edits on unrelated resources.
        resources.add(('live_tour_ledger', 'invoices'))
    return sorted(resources)


def begin_action(conn, action, payload, expected_revision, idempotency_key, counter_day, *, compact=False):
    independent = action in INDEPENDENT and not payload.get('start_now') and not any(row.get('start_now') for row in payload.get('bookings', []))
    lock(conn, shared=independent)
    conn.info['live_tour_exclusive'] = not independent
    # Lock discovery reads only collections inspected by action_resources.
    # In particular, do not decode/copy audit history and every idempotency
    # receipt twice while holding the shared fence. The authoritative full
    # read below still runs after resource locking and revalidates this set.
    discovery = LOCK_DISCOVERY_COLLECTIONS - {'invoices'} if compact and not payload.get('invoice_id') else LOCK_DISCOVERY_COLLECTIONS
    state, _, _ = read(conn, collections=discovery)
    resources = action_resources(state, action, payload, idempotency_key)
    try:
        concurrency.lock_resources(conn, resources, wait=False)
    except TimeoutError:
        raise HTTPException(503, 'Đối tượng đang được cập nhật. Vui lòng thử lại.', headers={'Retry-After': '1'}) from None
    if compact and action in PAYMENT_ACTIONS:
        state, revision, versions = read(conn, payment_key=idempotency_key)
    elif compact and action not in {'backup', 'restore'}:
        profile = 'operational' if action in OPERATIONAL_ACTIONS else 'adjustment' if action in ADJUSTMENT_ACTIONS else None
        state, revision, versions = read(conn, receipt_key=idempotency_key, profile=profile)
    else:
        state, revision, versions = read(conn)
    if action_resources(state, action, payload, idempotency_key) != resources:
        raise HTTPException(409, 'Đối tượng đã đổi. Hãy làm mới rồi thao tác lại.')
    if independent and state.get('counter_business_date') != counter_day:
        raise HTTPException(409, 'Bảng tua đang chuyển ngày. Hãy làm mới rồi thử lại.')
    fresh = expected_revision == revision
    if independent and expected_revision is not None and expected_revision <= revision:
        mapping = {'live_tour_employee':'employees','live_tour_customer':'customers','live_tour_pending':'pending','live_tour_invoices':'invoices'}
        observed = [(mapping[domain], value) for domain,value in resources if domain in mapping]
        fresh = state.get('_configuration_revision', 0) <= expected_revision and all(versions.get(key, 0) <= expected_revision for key in observed)
    conn.info['live_tour_resources'] = resources
    return state, revision, fresh


def write(conn, before, after, actor):
    for collection in relational.RESOURCE_COLLECTIONS:
        for row in after.get(collection, []):
            row.setdefault('id', str(uuid4()))
    before_meta, old = relational._split(before)
    after_meta, new = relational._split(after)
    payment = isinstance(before, _PaymentSnapshot)
    scoped = isinstance(before, _ScopedSnapshot)
    appends = before.appends if scoped else frozenset()
    if payment:
        # Projected headers must never replace canonical invoice/history rows.
        for key, prior in list(old.items()):
            if key[0] in {'invoices', 'invoice_changes'}:
                if new.get(key) != prior:
                    raise RuntimeError('Checkout attempted to edit a historical invoice')
                del old[key]
                del new[key]
    if scoped:
        if any(old.get(key) != new.get(key) and key[0] not in before.writable for key in set(old) | set(new)):
            raise RuntimeError('Live Tour exceeded its certified write set')
        if any(key[0] in appends for key in old):
            raise RuntimeError('Append-only history must not load historical rows')
    if not conn.info.get('live_tour_exclusive', True):
        locked = set(conn.info.get('live_tour_resources', []))
        domains = {'employees':'live_tour_employee','customers':'live_tour_customer','pending':'live_tour_pending','invoices':'live_tour_invoices'}
        for key in set(old) | set(new):
            prior, current = old.get(key), new.get(key)
            if prior is None or prior == current or current is not None and prior[1] == current[1]:
                continue
            if key[0] in domains and (domains[key[0]],key[1]) not in locked:
                raise HTTPException(409, 'Phạm vi giao dịch đã đổi. Hãy làm mới rồi thử lại.')
        allowed_meta = {'updated_at','counter_business_date','bill_counters','idempotency','manual_order_active'}
        if before_meta.get('manual_order_active') != after_meta.get('manual_order_active') and after_meta.get('manual_order_active') is not False:
            raise HTTPException(409, 'Chỉ tác vụ sắp xếp toàn bảng được bật thứ tự thủ công.')
        if any(before_meta.get(key) != value and key not in allowed_meta for key,value in after_meta.items()):
            raise HTTPException(409, 'Cấu hình đã đổi. Hãy làm mới rồi thử lại.')
    # Allocate the publication revision at commit time. The short metadata row
    # lock also orders commits, avoiding a missed revision from sequence gaps.
    changes = {key: value for key, value in after_meta.items() if before_meta.get(key) != value and key != 'idempotency'}
    receipts = {key: value for key, value in after_meta.get('idempotency', {}).items() if before_meta.get('idempotency', {}).get(key) != value}
    removed_receipts = sorted(set(before_meta.get('idempotency', {})) - set(after_meta.get('idempotency', {})))
    receipt_patch = " || jsonb_build_object('idempotency',(COALESCE(payload->'idempotency','{}'::jsonb) - CAST(:removed_receipts AS text[])) || CAST(:receipts AS jsonb))" if receipts or removed_receipts else ''
    configuration_patch = " || jsonb_build_object('_configuration_revision',aggregate_revision+1)" if conn.info.get('live_tour_exclusive', True) else ''
    revision = int(conn.execute(text(f"""
        UPDATE {relational.META_TABLE}
        SET payload=payload || CAST(:patch AS jsonb){receipt_patch}{configuration_patch},
            aggregate_revision=aggregate_revision+1, updated_at=NOW(), payload_hash='active'
        WHERE singleton=1 RETURNING aggregate_revision
    """), {'patch': relational._json(changes), 'receipts': relational._json(receipts), 'removed_receipts': removed_receipts}).scalar_one())
    ordinal_updates = {}
    append_ordinals = {}
    if scoped:
        # The metadata row above serializes publication, including other
        # writers of the audit log. Allocate positions after taking that lock.
        for kind in sorted(appends):
            entries = sorted(((key, value) for key, value in new.items() if key[0] == kind), key=lambda item: item[1][0])
            if entries:
                first_ordinal = int(conn.execute(text(
                    f'SELECT COALESCE(MAX(ordinal),-1)+1 FROM {relational.RESOURCE_TABLES[kind]} WHERE deleted_at IS NULL'
                )).scalar_one())
                append_ordinals.update({key:first_ordinal+index for index,(key,_) in enumerate(entries)})
    for key in sorted(set(old) | set(new)):
        previous = old.get(key)
        current = new.get(key)
        if previous == current:
            continue
        kind, identifier = key
        table = relational.RESOURCE_TABLES[kind]
        if current is None:
            conn.execute(text(f'UPDATE {table} SET deleted_at=NOW(),aggregate_revision=:revision,resource_revision=resource_revision+1 WHERE resource_id=:id'), {'id': identifier, 'revision': revision})
        elif previous is not None and previous[1] == current[1]:
            ordinal_updates.setdefault(table, []).append({'resource_id': identifier, 'ordinal': current[0]})
        else:
            ordinal, payload = current
            if scoped and kind in appends:
                if previous is not None:
                    raise RuntimeError('Checkout ledger writes must append')
                ordinal = append_ordinals[key]
            conn.execute(text(f"""INSERT INTO {table}(resource_id,ordinal,payload,payload_hash,aggregate_revision)
                VALUES(:id,:ordinal,CAST(:payload AS jsonb),:hash,:revision)
                ON CONFLICT(resource_id) DO UPDATE SET ordinal=EXCLUDED.ordinal,payload=EXCLUDED.payload,
                payload_hash=EXCLUDED.payload_hash,aggregate_revision=EXCLUDED.aggregate_revision,
                resource_revision={table}.resource_revision+1,deleted_at=NULL,updated_at=NOW()"""),
                {'id': identifier, 'ordinal': ordinal, 'payload': relational._json(payload), 'hash': relational._digest(payload), 'revision': revision})
        if kind == 'employees':
            conn.execute(text(f"""INSERT INTO {relational.BOARD_HISTORY_TABLE}(aggregate_revision,employee_id,employee_name,actor,action,before_ordinal,after_ordinal,before_payload,after_payload)
                VALUES(:revision,:id,:name,:actor,'update',:bo,:ao,CAST(:before AS jsonb),CAST(:after AS jsonb))"""),
                {'revision':revision,'id':identifier,'name':(current or previous)[1].get('name',''),'actor':actor,
                 'bo':previous[0] if previous else None,'ao':current[0] if current else None,
                 'before':relational._json(previous[1] if previous else None),'after':relational._json(current[1] if current else None)})
    # Evicting one item from a full audit ring shifts every retained ordinal.
    # Preserve the exact ordering in one statement per collection instead of
    # thousands of network round trips while holding the transaction locks.
    # The metadata update above already serializes publication through commit.
    for table, updates in sorted(ordinal_updates.items()):
        conn.execute(text(f"""
            UPDATE {table} AS target SET ordinal=source.ordinal
            FROM jsonb_to_recordset(CAST(:updates AS jsonb))
                 AS source(resource_id text, ordinal integer)
            WHERE target.resource_id=source.resource_id
        """), {'updates': relational._json(updates)})
    if scoped and after.get('audit'):
        from vera_web_v2_live_tour import MAX_AUDIT
        table = relational.RESOURCE_TABLES['audit']
        conn.execute(text(f"""UPDATE {table} SET deleted_at=NOW(),aggregate_revision=:revision,
            resource_revision=resource_revision+1 WHERE resource_id IN (
                SELECT resource_id FROM {table} WHERE deleted_at IS NULL
                ORDER BY ordinal DESC,resource_id DESC OFFSET :limit)
            AND deleted_at IS NULL"""), {'revision':revision,'limit':MAX_AUDIT})
    return revision
