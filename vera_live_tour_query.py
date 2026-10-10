"""Indexed, read-only Live Tour lists from the authoritative resource snapshot.

Projection installation is a deploy-only, transaction-owned migration. A stale
projection (including a write by an older release) disables this read path in the
same MVCC snapshot as the page/count. Shadow data is never promoted implicitly.
All functions reuse their caller's connection; none acquire a business lock.
"""
from __future__ import annotations

from copy import deepcopy
from datetime import datetime
import math
import re
import unicodedata

from sqlalchemy import text

import vera_live_tour_lists as lists
import vera_live_tour_relational as relational
import vera_versioned_schema as versioned

COMPONENT = 'live_tour_query'
VERSION = 1
GROUPS = {
    'customers': ('customers',), 'pending': ('pending',), 'invoices': ('invoices',),
    'reports': ('reports',),
    'history': ('audit', 'break_events', 'pending_changes', 'invoice_changes', 'customer_changes', 'backups'),
}
BASE = ('employees', 'rooms', 'services', 'combos')
HISTORY = frozenset(GROUPS['history'])


def schema_ready(conn):
    return versioned._ready(conn, COMPONENT, VERSION)


def _day(value):
    try:
        moment = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return (moment.replace(tzinfo=lists.VN) if moment.tzinfo is None else moment.astimezone(lists.VN)).date().isoformat()
    except (ValueError, TypeError):
        return ''


def _number(value):
    try:
        value = float(value or 0)
        return value if math.isfinite(value) else 0
    except (ValueError, TypeError):
        return 0


def _report_fold(value):
    # Match tourNameKey/normalizeSearchText, including their combining range.
    value = unicodedata.normalize('NFD', str(value or ''))
    value = ''.join(char for char in value if not '\u0300' <= char <= '\u036f')
    return ' '.join(value.replace('đ', 'd').replace('Đ', 'd').lower().split())


def _report_normalize(value):
    return ' '.join(''.join(char if unicodedata.category(char)[0] in {'L', 'N'} else ' '
                            for char in _report_fold(value)).split())


def _report_day(value):
    value = str(value or '').strip()
    legacy = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', value, flags=re.ASCII)
    if legacy:
        day, month, year = legacy.groups()
        value = f'{year}-{month.zfill(2)}-{day.zfill(2)}'
    return _day(value)


def _report_customer_terms(value):
    value = re.sub(r'[+(]*\d(?:[\d\s().-]*\d)?\)*', lambda match: re.sub(r'\D', '', match.group(), flags=re.ASCII), _report_fold(value), flags=re.ASCII)
    terms = value.split()
    numbers = [term for term in terms if re.fullmatch('[0-9]+', term)]
    return ' '.join(term for term in terms if term not in numbers), numbers


def _report_phrase(field, query):
    terms = _report_normalize(query).split()
    words = _report_normalize(field).split()
    return not terms or any(all(start + i < len(words) and (words[start+i].startswith(term) if i == len(terms)-1 else words[start+i] == term)
                               for i, term in enumerate(terms)) for start in range(len(words)))


def _report_customer_matches(row, value):
    name, numbers = _report_customer_terms(value)
    phone = re.sub(r'\D', '', str(row.get('phone') or row.get('customer_phone') or ''), flags=re.ASCII)
    local = lambda digits: '0' + digits[2:] if re.fullmatch('84[0-9]{9}', digits) else digits
    return _report_phrase(row.get('name') or row.get('customer_name'), name) and all(term in phone or local(term) in local(phone) for term in numbers)


def project(kind, raw):
    """Use the existing Python normalization, without SQL locale/unaccent drift."""
    row = raw
    if kind in HISTORY:
        row = {**raw, 'effective_at': raw.get('effective_at') or raw.get('at') or raw.get('created_at') or raw.get('timestamp'),
               'customer_name': raw.get('customer_name') or (raw.get('before') or {}).get('name') or (raw.get('after') or {}).get('name'),
               'entries': [{'employee_name': raw.get('employee_name') or raw.get('actor'),
                            'service': raw.get('service') or raw.get('action') or raw.get('event_type')}]}
    phone = re.sub(r'\D', '', str(row.get('phone') or row.get('customer_phone') or ''))
    report_phone = re.sub(r'\D', '', str(row.get('phone') or row.get('customer_phone') or ''), flags=re.ASCII)
    return {
        'report_customer': _report_normalize(row.get('name') or row.get('customer_name')),
        'report_phone': report_phone, 'report_local_phone': '0' + report_phone[2:] if re.fullmatch('84[0-9]{9}', report_phone) else report_phone,
        'report_entries': [{'employee': _report_normalize(entry.get('employee_name')), 'service': _report_normalize(entry.get('service'))} for entry in row.get('entries') or [row]],
        'report_day': _report_day(row.get('effective_at') or row.get('booked_at') or row.get('created_at') or row.get('business_date')),
        'report_invoice_day': _report_day(row.get('effective_at') or row.get('business_date')),
        'invoice_total': _number(raw['invoice_total']) if raw.get('invoice_total') is not None else None,
        'invoice_discount': _number(raw['invoice_discount']) if raw.get('invoice_discount') is not None else None,
        'customer_id': str(raw.get('id') or '') if kind == 'customers' else str(raw.get('customer_id') or ''),
        'customer': lists.normalize(row.get('name') or row.get('customer_name')),
        'phone': phone, 'local_phone': '0' + phone[2:] if re.fullmatch(r'84\d{9}', phone) else phone,
        'entries': [{'employee': lists.normalize(entry.get('employee_name')), 'service': lists.normalize(entry.get('service'))}
                    for entry in row.get('entries') or [row]],
        'bills': [str(number).lower() for number in lists.invoice_numbers(row)],
        'report_bills': [str(number).lower() for number in lists.invoice_numbers(row) if number],
        'day': _day(row.get('effective_at') or row.get('booked_at') or row.get('created_at') or row.get('business_date')),
        'invoice_day': _day(row.get('effective_at') or row.get('business_date')),
        'hidden_customer': bool(raw.get('deleted_at')),
        'total': _number(raw.get('total')), 'tip': _number(raw.get('tip')), 'discount': _number(raw.get('discount')),
        'invoice_id': str(raw.get('invoice_id') or ''), 'bill_no': str(raw.get('bill_no') or ''),
        'id': str(raw.get('id') or ''), 'employee_id': str(raw.get('employee_id') or ''),
        'employee_name': str(raw.get('employee_name') or ''),
        'employee': str(raw.get('employee_name') or '').strip() or 'Chưa xác định',
        'requested': str(raw.get('request') or '').strip().lower() == 'yc',
        'combo': bool(raw.get('combo_units') or re.search('combo', str(raw.get('service') or ''), re.I)),
        'combo_sale': bool(raw.get('purchased_combo_id')),
    }


def ensure_schema(conn):
    """Called by deployment, never by a read or ordinary resource mutation."""
    def migrate(connection):
        # Take all relation DDL locks before backfill. Concurrent writes either
        # commit before the backfill snapshot or wait until the marker commits.
        for table in relational.RESOURCE_TABLES.values():
            connection.execute(text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS query_data jsonb NOT NULL DEFAULT '{{}}'::jsonb, ADD COLUMN IF NOT EXISTS query_hash text NOT NULL DEFAULT ''"))
        for kind, table in relational.RESOURCE_TABLES.items():
            last = ''
            while True:
                rows = connection.execute(text(f'SELECT resource_id,payload,payload_hash FROM {table} WHERE resource_id>:last ORDER BY resource_id LIMIT 250'), {'last': last}).mappings().all()
                if not rows:
                    break
                batch = [{'id': row['resource_id'], 'hash': row['payload_hash'], 'query': project(kind, row['payload'])} for row in rows]
                connection.execute(text(f'''UPDATE {table} AS target SET query_data=source.query,query_hash=source.hash
                    FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS source(id text,hash text,query jsonb)
                    WHERE target.resource_id=source.id'''), {'rows': relational._json(batch)})
                last = rows[-1]['resource_id']
            # The partial stale index is the compatibility/parity gate. Old
            # writers need not know about this projection to invalidate it.
            connection.execute(text(f'CREATE INDEX IF NOT EXISTS idx_{table}_query_stale ON {table}(resource_id) WHERE deleted_at IS NULL AND query_hash IS DISTINCT FROM payload_hash'))
            connection.execute(text(f'CREATE INDEX IF NOT EXISTS idx_{table}_query_order ON {table}(ordinal,resource_id) WHERE deleted_at IS NULL'))
            if kind in {'customers', 'pending', 'invoices', 'reports', 'combo_usage'}:
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_query_customer ON {table}((query_data->>'customer_id'),ordinal,resource_id) WHERE deleted_at IS NULL"))
            if kind in set(GROUPS['history']) | {'pending', 'invoices', 'reports'}:
                field = 'invoice_day' if kind in {'invoices', 'reports'} else 'day'
                connection.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_query_day ON {table}((query_data->>'{field}'),ordinal,resource_id) WHERE deleted_at IS NULL"))
                if kind in {'pending', 'invoices', 'reports'}:
                    connection.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{table}_query_report_day ON {table}((query_data->>'report_{field}'),ordinal,resource_id) WHERE deleted_at IS NULL"))
    versioned.ensure(conn, COMPONENT, VERSION, migrate)
    # Re-running the explicit deploy gate repairs rows dirtied by old workers
    # between a previous migration and their restart. Never called by requests.
    repair_projections(conn)


def repair_projections(conn, *, max_batches=1000):
    """Explicit, bounded repair. Hash CAS prevents projecting over newer data."""
    if not schema_ready(conn):
        raise RuntimeError('Live Tour query schema must be installed before repair')
    repaired = 0
    for kind, table in sorted(relational.RESOURCE_TABLES.items(), key=lambda item: item[1]):
        for _ in range(max_batches):
            rows = conn.execute(text(f"SELECT resource_id,payload,payload_hash FROM {table} WHERE deleted_at IS NULL AND query_hash IS DISTINCT FROM payload_hash ORDER BY resource_id LIMIT 250")).mappings().all()
            if not rows:
                break
            batch = [{'id': row['resource_id'], 'hash': row['payload_hash'], 'query': project(kind, row['payload'])} for row in rows]
            result = conn.execute(text(f"""UPDATE {table} AS target SET query_data=source.query,query_hash=source.hash
                FROM jsonb_to_recordset(CAST(:rows AS jsonb)) AS source(id text,hash text,query jsonb)
                WHERE target.resource_id=source.id AND target.payload_hash=source.hash
                  AND target.query_hash IS DISTINCT FROM target.payload_hash"""), {'rows': relational._json(batch)})
            repaired += result.rowcount
        else:
            raise RuntimeError('Live Tour query repair batch limit reached; retry in a quiet maintenance window')
    return {'repaired': repaired}


def verify_projections(conn):
    if not schema_ready(conn):
        return {'ok': False, 'schema_ready': False}
    parts = [f"SELECT COUNT(*) AS count FROM {table} WHERE deleted_at IS NULL AND query_hash IS DISTINCT FROM payload_hash" for table in relational.RESOURCE_TABLES.values()]
    stale = int(conn.execute(text('SELECT SUM(count) FROM (' + ' UNION ALL '.join(parts) + ') counts')).scalar_one())
    return {'ok': stale == 0, 'schema_ready': True, 'stale_rows': stale}


def allowed_groups(panel, grants):
    allowed = {
        'audit': grants.get('can_history_view'), 'break_events': grants.get('can_history_view'),
        'pending_changes': grants.get('can_history_view') and grants.get('can_pending_view') and grants.get('can_invoice_view'),
        'invoice_changes': grants.get('can_history_view') and grants.get('can_paid_invoice_view'),
        'customer_changes': grants.get('can_history_view') and grants.get('can_customers_view'),
        'backups': grants.get('can_backup'),
    }
    return tuple(kind for kind in GROUPS[panel] if allowed.get(kind, True))


def _phrase(field, value, params, key, *, report=False):
    terms = (_report_normalize(value) if report else lists.normalize(value)).split()
    if not terms:
        return 'TRUE'
    params[key] = '(^| )' + ' '.join(re.escape(term) for term in terms)
    # Normalized strings have one ASCII separator; only the last word may be a prefix.
    return f"({field}) ~ :{key}"


def _customer(field, value, params, key, *, report=False):
    if report:
        name_query, numbers = _report_customer_terms(value)
    else:
        compact = re.sub(r'[+(]*\d(?:[\d\s().-]*\d)?\)*', lambda match: re.sub(r'\D', '', match.group()), str(value or ''))
        terms = lists.normalize(compact).split()
        name_query, numbers = ' '.join(term for term in terms if not term.isdigit()), [term for term in terms if term.isdigit()]
    field_prefix = 'report_' if report else ''
    result = [_phrase(f"{field}->>'{field_prefix}customer'", name_query, params, key + '_name', report=report)]
    for index, term in enumerate(numbers):
        name = f'{key}_phone_{index}'
        params[name] = term
        params[name + '_local'] = '0' + term[2:] if re.fullmatch(r'84\d{9}', term) else term
        result.append(f"(strpos({field}->>'{field_prefix}phone',:{name})>0 OR strpos({field}->>'{field_prefix}local_phone',:{name}_local)>0)")
    return ' AND '.join(result)


def predicate(kind, filters, params, *, alias='r', prefix='', customer_pii=True, report_mode=False):
    q = alias + '.query_data'
    where = [f'{alias}.deleted_at IS NULL']
    if kind == 'customers':
        where.append(f"NOT ({q}->>'hidden_customer')::boolean")
        for name, values in [('customer_id', [filters.get('customer_id')] if filters.get('customer_id') else []), ('customer_ids', sorted(filters.get('customer_ids') or []))]:
            if values:
                params[prefix + name] = values
                where.append(f"{q}->>'customer_id'=ANY(CAST(:{prefix + name} AS text[]))")
        where.append(_customer(q, filters.get('search'), params, prefix + 'search'))
        return ' AND '.join(where)
    field_prefix = 'report_' if report_mode else ''
    day = f"{q}->>'{field_prefix}{'invoice_day' if kind in {'invoices', 'reports'} else 'day'}'"
    for name, operator in [('date_from', '>='), ('date_to', '<='), ('date', '=')]:
        if filters.get(name):
            params[prefix + name] = filters[name]
            where.extend([f"{day}<>''", f'{day}{operator}:{prefix + name}'])
    if filters.get('bill_no'):
        params[prefix + 'bill_no'] = filters['bill_no'].strip().lower()
        where.append(f"EXISTS (SELECT 1 FROM jsonb_array_elements_text({q}->'{field_prefix}bills') bill WHERE strpos(bill,:{prefix}bill_no)>0)")
    if filters.get('customer'):
        if not customer_pii:
            matcher = _report_customer_matches if report_mode else lists.customer_matches
            where.append('TRUE' if matcher({}, filters['customer']) else 'FALSE')
        else:
            where.append(_customer(q, filters['customer'], params, prefix + 'customer', report=report_mode))
    if filters.get('employee') or filters.get('service'):
        employee = _phrase("entry->>'employee'", filters.get('employee'), params, prefix + 'employee', report=report_mode)
        service = _phrase("entry->>'service'", filters.get('service'), params, prefix + 'service', report=report_mode)
        where.append(f"EXISTS (SELECT 1 FROM jsonb_array_elements({q}->'{field_prefix}entries') entry WHERE {employee} AND {service})")
    for name in ('total_amount', 'tip_amount'):
        if filters.get(name) is not None:
            params[prefix + name] = filters[name]
            field = 'total' if name == 'total_amount' else 'tip'
            where.append(f"({q}->>'{field}')::numeric=:{prefix + name}")
    if filters.get('customer_id'):
        params[prefix + 'customer_id'] = str(filters['customer_id'])
        where.append(f"{q}->>'customer_id'=:{prefix}customer_id")
    return ' AND '.join(where)


def _guard(kinds):
    stale = ' OR '.join(f'EXISTS (SELECT 1 FROM {relational.RESOURCE_TABLES[kind]} WHERE deleted_at IS NULL AND query_hash IS DISTINCT FROM payload_hash)' for kind in sorted(set(kinds))) or 'FALSE'
    return f"ready AS MATERIALIZED (SELECT NOT ({stale}) AND COALESCE((SELECT payload->>'_resource_ready'='true' FROM {relational.META_TABLE} WHERE singleton=1),false) AS ok)"


def _base_ctes(kinds):
    return [_guard(kinds), f"meta AS (SELECT payload-'idempotency' AS payload,aggregate_revision FROM {relational.META_TABLE} WHERE singleton=1 AND (SELECT ok FROM ready))"]


def _state_sql(parts):
    empty = {kind: [] for kind in relational.RESOURCE_COLLECTIONS}
    fields = ','.join("'" + kind + "'," + expression for kind, expression in parts.items())
    return f"COALESCE((SELECT payload FROM meta),'{{}}'::jsonb) || '{relational._json(empty)}'::jsonb" + (f' || jsonb_build_object({fields})' if fields else '')


def _all_rows(kind):
    table = relational.RESOURCE_TABLES[kind]
    return f"(SELECT COALESCE(jsonb_agg(payload ORDER BY ordinal,resource_id),'[]'::jsonb) FROM {table} WHERE deleted_at IS NULL AND (SELECT ok FROM ready))"


def _page_rows(kind, cte, *, ascending=True):
    table = relational.RESOURCE_TABLES[kind]
    return f"(SELECT COALESCE(jsonb_agg(t.payload ORDER BY p.ordinal {'ASC' if ascending else 'DESC'},p.resource_id {'ASC' if ascending else 'DESC'}),'[]'::jsonb) FROM {cte} p JOIN {table} t USING(resource_id))"


def _execute(conn, ctes, parts, extra, params):
    statement = 'WITH ' + ',\n'.join(ctes) + f" SELECT (SELECT ok FROM ready) AS ready,(SELECT aggregate_revision FROM meta) AS revision,{_state_sql(parts)} AS state" + extra
    result = conn.execute(text(statement), params).mappings().one()
    if not result['ready']:
        return None
    result = dict(result)
    for employee in result.get('employee_totals') or []:
        for field in ('service', 'tip', 'total'):
            employee[field] = math.floor(float(employee[field])*100 + .5)/100
    return result


def read_collection(conn, panel, *, page, page_size, filters, grants):
    if relational.mode() != 'active' or not schema_ready(conn):
        return None
    kinds = allowed_groups(panel, grants)
    dependencies = set(BASE)
    if panel == 'customers':
        dependencies.add('pending')
    if panel == 'reports':
        dependencies.add('invoices')
    ctes = _base_ctes(set(kinds) | dependencies)
    params = {'limit': page_size, 'offset': (page - 1) * page_size}
    parts = {kind: _all_rows(kind) for kind in dependencies - {'invoices'}}
    counts = []
    pii = bool(grants.get('can_customers_view') or grants.get('can_invoice_view') or grants.get('can_paid_invoice_view'))
    for kind in kinds:
        where = predicate(kind, filters, params, prefix=kind + '_', customer_pii=pii or kind == 'pending')
        ctes.append(f"f_{kind} AS MATERIALIZED (SELECT resource_id,ordinal,query_data FROM {relational.RESOURCE_TABLES[kind]} r WHERE (SELECT ok FROM ready) AND {where})")
        ctes.append(f'p_{kind} AS (SELECT resource_id,ordinal FROM f_{kind} ORDER BY ordinal DESC,resource_id DESC LIMIT :limit OFFSET :offset)')
        parts[kind] = _page_rows(kind, 'p_' + kind)
        counts.extend([f"'{kind}'", f'(SELECT COUNT(*) FROM f_{kind})'])
    if panel == 'reports':
        parts['invoices'] = f"(SELECT COALESCE(jsonb_agg(i.payload ORDER BY i.ordinal,i.resource_id),'[]'::jsonb) FROM {relational.RESOURCE_TABLES['invoices']} i WHERE i.deleted_at IS NULL AND i.resource_id IN (SELECT r.query_data->>'invoice_id' FROM f_reports r JOIN p_reports USING(resource_id)))"
    extra = ',jsonb_build_object(' + ','.join(counts) + ') AS totals' if counts else ", '{}'::jsonb AS totals"
    if panel == 'reports':
        extra += ", (SELECT jsonb_build_object('totalRevenue',COALESCE(sum((query_data->>'total')::numeric),0),'tip',COALESCE(sum((query_data->>'tip')::numeric),0),'serviceRevenue',COALESCE(sum((query_data->>'total')::numeric-(query_data->>'tip')::numeric),0),'invoiceCount',COUNT(DISTINCT COALESCE(NULLIF(query_data->>'invoice_id',''),NULLIF(query_data->>'bill_no','')))) FROM f_reports) AS report_totals"
    return _execute(conn, ctes, parts, extra, params)


def read_customer_history(conn, customer_id, grants):
    """Preserve the complete-history DTO, but transfer only this customer's rows."""
    if relational.mode() != 'active' or not schema_ready(conn):
        return None
    kinds = {'customers', 'combo_usage'}
    if grants.get('can_paid_invoice_view'):
        kinds.add('invoices')
    if grants.get('can_reports_view'):
        kinds.add('reports')
    if grants.get('can_pending_view') and grants.get('can_invoice_view'):
        kinds.add('pending')
    ctes = _base_ctes(kinds)
    parts = {}
    for kind in kinds:
        parts[kind] = f"(SELECT COALESCE(jsonb_agg(payload ORDER BY ordinal,resource_id),'[]'::jsonb) FROM {relational.RESOURCE_TABLES[kind]} WHERE deleted_at IS NULL AND query_data->>'customer_id'=:customer_id AND (SELECT ok FROM ready))"
    return _execute(conn, ctes, parts, '', {'customer_id': str(customer_id).strip()})


def read_reports(conn, *, tab, page, page_size, filters, grants):
    if tab == 'performance' or relational.mode() != 'active' or not schema_ready(conn):
        return None
    source = 'invoices' if tab == 'invoices' else 'reports'
    pending_access = bool(grants.get('can_pending_view') and grants.get('can_invoice_view'))
    kinds = {'invoices', source} | ({'pending'} if pending_access else set())
    ctes = _base_ctes(kinds)
    params = {'limit': page_size, 'offset': (page - 1) * page_size}
    pii = bool(grants.get('can_customers_view') or grants.get('can_invoice_view') or grants.get('can_paid_invoice_view'))
    where = predicate(source, filters, params, customer_pii=pii, report_mode=True)
    if source == 'invoices' and not grants.get('can_paid_invoice_view'):
        where += ' AND FALSE'
    if tab == 'tip':
        where += " AND (r.query_data->>'tip')::numeric>0"
    if tab == 'combos':
        where += " AND ((r.query_data->>'combo')::boolean OR COALESCE((i.query_data->>'combo_sale')::boolean,false))"
    table = relational.RESOURCE_TABLES[source]
    invoices = relational.RESOURCE_TABLES['invoices']
    join_key = "r.resource_id" if source == 'invoices' else "r.query_data->>'invoice_id'"
    metrics_key = "COALESCE(NULLIF(r.query_data->>'invoice_id',''),r.query_data->>'id')" if source == 'reports' and grants.get('can_paid_invoice_view') else join_key
    ctes.append(f'''filtered AS MATERIALIZED (SELECT r.resource_id,r.ordinal,r.query_data,
        mi.query_data AS invoice_data FROM {table} r LEFT JOIN {invoices} i ON i.resource_id={join_key} AND i.deleted_at IS NULL
        LEFT JOIN {invoices} mi ON mi.resource_id={metrics_key} AND mi.deleted_at IS NULL
        WHERE (SELECT ok FROM ready) AND {where})''')
    ctes.append('page_rows AS (SELECT resource_id,ordinal FROM filtered ORDER BY ordinal,resource_id LIMIT :limit OFFSET :offset)')
    ctes.append('''invoice_groups AS (SELECT COALESCE(NULLIF(query_data->>'invoice_id',''),NULLIF(query_data->>'bill_no',''),NULLIF(query_data->>'id',''),resource_id) AS identity,
        COALESCE((ARRAY_AGG(COALESCE(invoice_data->'total',query_data->'invoice_total') ORDER BY ordinal DESC,resource_id DESC) FILTER (WHERE invoice_data IS NOT NULL OR query_data->>'invoice_total' IS NOT NULL))[1]::numeric,SUM((query_data->>'total')::numeric)) AS total,
        COALESCE((ARRAY_AGG(COALESCE(invoice_data->'discount',query_data->'invoice_discount') ORDER BY ordinal DESC,resource_id DESC) FILTER (WHERE invoice_data IS NOT NULL OR query_data->>'invoice_discount' IS NOT NULL))[1]::numeric,SUM((query_data->>'discount')::numeric)) AS discount
        FROM filtered GROUP BY 1)''')
    ctes.append('''employee_groups AS (SELECT query_data->>'employee' AS employee,
        SUM((query_data->>'total')::numeric-(query_data->>'tip')::numeric) AS service,
        SUM((query_data->>'tip')::numeric) AS tip,SUM((query_data->>'total')::numeric) AS total,
        COUNT(*) FILTER (WHERE NOT (query_data->>'requested')::boolean) AS "tourRows",
        COUNT(*) FILTER (WHERE (query_data->>'requested')::boolean) AS "requestRows",COUNT(*) AS rows
        FROM filtered GROUP BY 1)''')
    if pending_access:
        pending_where = predicate('pending', filters, params, prefix='pending_', report_mode=True)
        pending_count = f"(SELECT COUNT(*) FROM {relational.RESOURCE_TABLES['pending']} r WHERE (SELECT ok FROM ready) AND {pending_where})"
    else:
        pending_count = 'NULL'
    parts = {source: _page_rows(source, 'page_rows')}
    if source == 'reports':
        parts['invoices'] = f"(SELECT COALESCE(jsonb_agg(i.payload ORDER BY i.ordinal,i.resource_id),'[]'::jsonb) FROM {invoices} i WHERE i.deleted_at IS NULL AND i.resource_id IN (SELECT f.query_data->>'invoice_id' FROM filtered f JOIN page_rows USING(resource_id)))"
    extra = f''', (SELECT COUNT(*) FROM filtered) AS total,
        (SELECT jsonb_build_object('totalRevenue',COALESCE(SUM((query_data->>'total')::numeric),0),
            'tip',COALESCE(SUM((query_data->>'tip')::numeric),0),
            'serviceRevenue',COALESCE(SUM((query_data->>'total')::numeric-(query_data->>'tip')::numeric),0),
            'invoiceCount',COUNT(DISTINCT NULLIF(btrim(COALESCE(NULLIF(query_data->>'invoice_id',''),query_data->>'bill_no')),'')),
            'tipEmployeeCount',COUNT(DISTINCT COALESCE(NULLIF(query_data->>'employee_id',''),query_data->>'employee_name')),
            'zeroInvoices',(SELECT COUNT(*) FROM invoice_groups WHERE total=0),
            'discount',(SELECT COALESCE(SUM(discount),0) FROM invoice_groups),
            'pendingInvoiceCount',{pending_count}) FROM filtered) AS summary,
        (SELECT COALESCE(jsonb_agg(to_jsonb(e) ORDER BY service DESC,tip DESC,employee),'[]'::jsonb) FROM employee_groups e) AS employee_totals'''
    return _execute(conn, ctes, parts, extra, params)


def matches_report(row, filters, *, invoice_dates=True):
    if any(filters.get(key) is not None and _number(row.get(field)) != filters[key]
           for key, field in [('total_amount', 'total'), ('tip_amount', 'tip')]):
        return False
    if filters.get('bill_no') and not any(filters['bill_no'].strip().lower() in str(number).lower() for number in lists.invoice_numbers(row) if number):
        return False
    if any(filters.get(key) for key in ('date', 'date_from', 'date_to')):
        raw = row.get('effective_at') or row.get('business_date') if invoice_dates else row.get('effective_at') or row.get('booked_at') or row.get('created_at') or row.get('business_date')
        day = _report_day(raw)
        if (filters.get('date') and day != filters['date'] or filters.get('date_from') and (not day or day < filters['date_from'])
                or filters.get('date_to') and (not day or day > filters['date_to'])):
            return False
    if filters.get('customer') and not _report_customer_matches(row, filters['customer']):
        return False
    return any(_report_phrase(entry.get('employee_name'), filters.get('employee')) and _report_phrase(entry.get('service'), filters.get('service')) for entry in row.get('entries') or [row])


def is_combo_report(row):
    return bool(row.get('combo_sale') or row.get('combo_units') or re.search('combo', str(row.get('service') or ''), re.I))


def report_page(public, state, *, tab, page, page_size, filters, performance):
    """Canonical fallback/reference contract; never serves a stale shadow mirror."""
    source = performance if tab == 'performance' else public['state']['invoices'] if tab == 'invoices' else public['report_rows']
    rows = [row for row in source if matches_report(row, filters, invoice_dates=tab != 'performance')]
    if tab == 'tip':
        rows = [row for row in rows if _number(row.get('tip')) > 0]
    elif tab == 'combos':
        rows = [row for row in rows if is_combo_report(row)]
    elif tab == 'performance' and filters.get('performance_timing') != 'all':
        timing = filters.get('performance_timing')
        rows = [row for row in rows if (_number(row.get('completion_delta_minutes')) < 0 if timing == 'early' else
                                       _number(row.get('completion_delta_minutes')) > 0 if timing == 'late' else
                                       _number(row.get('completion_delta_minutes')) == 0)]
    invoices = {row['id']: row for row in public['state']['invoices'] if row.get('id')}
    invoice_groups, employees = {}, {}
    for index, row in enumerate(rows):
        identity = row.get('invoice_id') or row.get('bill_no') or row.get('id') or f'row-{index}'
        group = invoice_groups.setdefault(identity, {'total': 0, 'discount': 0})
        group['total'] += _number(row.get('total'))
        group['discount'] += _number(row.get('discount'))
        invoice = invoices.get(row.get('invoice_id') or row.get('id'))
        if invoice is not None or row.get('invoice_total') is not None:
            group['invoice_total'] = _number(invoice.get('total') if invoice is not None else row.get('invoice_total'))
        if invoice is not None or row.get('invoice_discount') is not None:
            group['invoice_discount'] = _number(invoice.get('discount') if invoice is not None else row.get('invoice_discount'))
        name = str(row.get('employee_name') or '').strip() or 'Chưa xác định'
        employee = employees.setdefault(name, dict(employee=name, service=0, tip=0, total=0, tourRows=0, requestRows=0, rows=0))
        employee['total'] += _number(row.get('total'))
        employee['tip'] += _number(row.get('tip'))
        employee['service'] += _number(row.get('total')) - _number(row.get('tip'))
        employee['requestRows' if str(row.get('request') or '').strip().lower() == 'yc' else 'tourRows'] += 1
        employee['rows'] += 1
    total, tip = sum(_number(row.get('total')) for row in rows), sum(_number(row.get('tip')) for row in rows)
    summary = dict(totalRevenue=total, tip=tip, serviceRevenue=total-tip,
                   invoiceCount=len({str(row.get('invoice_id') or row.get('bill_no') or '').strip() for row in rows} - {''}),
                   zeroInvoices=sum(group.get('invoice_total', group['total']) == 0 for group in invoice_groups.values()),
                   discount=sum(group.get('invoice_discount', group['discount']) for group in invoice_groups.values()),
                   tipEmployeeCount=len({row.get('employee_id') or row.get('employee_name') or '' for row in rows}),
                   pendingInvoiceCount=sum(matches_report(row, filters, invoice_dates=False) for row in public['pending_payments'])
                   if public['capabilities'].get('pending_view') and public['capabilities'].get('invoice_view') else None)
    for employee in employees.values():
        for field in ('service', 'tip', 'total'):
            employee[field] = math.floor(employee[field]*100 + .5)/100
    selected = rows[(page-1)*page_size:page*page_size]
    ids = {row.get('invoice_id') or row.get('id') for row in selected}
    return {'rows': selected, 'invoices': [row for row in public['state']['invoices'] if row.get('id') in ids],
            'total': len(rows), 'summary': summary,
            'employee_totals': sorted(employees.values(), key=lambda value: (-value['service'], -value['tip'], value['employee']))}


if __name__ == '__main__':
    import argparse
    import json
    from vera_vps_concurrency_schema import _runtime_engine
    parser = argparse.ArgumentParser(description='Verify or repair only Live Tour read projections; financial payloads and mode flags remain unchanged.')
    parser.add_argument('--repair', action='store_true', help='Explicitly repair stale projections after all API/projection workers run the new release')
    args = parser.parse_args()
    engine = _runtime_engine()
    with engine.begin() as conn:
        conn.execute(text("SET LOCAL lock_timeout='5s'"))
        conn.execute(text("SET LOCAL statement_timeout='60s'"))
        repaired = repair_projections(conn) if args.repair else {}
        result = {**verify_projections(conn), **repaired}
    print(json.dumps(result))
    raise SystemExit(0 if result['ok'] else 1)
