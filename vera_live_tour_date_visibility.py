"""Detached response filtering; never trim the operational/payment snapshot."""
from __future__ import annotations

from copy import deepcopy

import vera_live_tour_date_policy as policy
import vera_live_tour_query as query


def row_day(section, row):
    # Date-only work: do not rebuild search/phone/entry indexes for every row.
    if section in {'invoices', 'reports'}:
        return query._report_day(row.get('effective_at') or row.get('business_date'))
    if section == 'history':
        raw = row.get('effective_at') or row.get('at') or row.get('created_at') or row.get('timestamp')
    else:
        raw = row.get('effective_at') or row.get('booked_at') or row.get('created_at') or row.get('business_date')
    return query._day(raw)


def filter_rows(rows, section, date_policy, now, requests=None):
    if date_policy is None:  # Internal callers retain their existing contract.
        return list(rows)
    return policy.filter_rows(date_policy, section, now, rows,
                              lambda row: row_day(section, row),
                              request=(requests or {}).get(section))


def unrestricted(date_policy, section):
    return date_policy is None or 'all' in date_policy.get('sections', {}).get(section, [])


def filter_state(state, date_policy, now, requests=None):
    """Keep section grants independent, including embedded historical snapshots.

    The result is a detached view. Callers calculate reservations and execute
    payments against the original state, never this filtered response.
    """
    if date_policy is None:
        return state
    result = dict(state)
    for section in ('pending', 'invoices', 'reports'):
        result[section] = filter_rows(state.get(section, []), section, date_policy, now, requests)
    for kind in ('audit', 'break_events', 'pending_changes', 'invoice_changes', 'customer_changes', 'backups'):
        result[kind] = filter_rows(state.get(kind, []), 'history', date_policy, now, requests)

    for kind, section in (('pending_changes', 'pending'), ('invoice_changes', 'invoices')):
        changes = []
        for original in result[kind]:
            change = deepcopy(original)
            for side in ('before', 'after'):
                row = change.get(side)
                if isinstance(row, dict) and not filter_rows([row], section, date_policy, now, requests):
                    change[side] = None
                    change['date_restricted'] = True
                reports = change.get('reports_' + side)
                if isinstance(reports, list):
                    change['reports_' + side] = filter_rows(reports, 'reports', date_policy, now, requests)
            # A denied source date cannot leak through summary/amount metadata.
            if change.get('date_restricted'):
                change = {key: value for key, value in change.items()
                          if key in {'id', 'at', 'actor', 'action', 'reason', 'pending_id', 'invoice_id',
                                     'before', 'after', 'date_restricted', 'reports_before', 'reports_after'}}
            changes.append(change)
        result[kind] = changes

    events = []
    for original in result['audit']:
        section = ('pending' if original.get('action') in {'pending_update', 'pending_delete', 'move_pending', 'finish_to_pending'}
                   else 'invoices' if original.get('action') in {'checkout', 'quick_checkout', 'paid_invoice_update',
                                                                'paid_invoice_delete', 'report_invoice_update', 'report_invoice_delete',
                                                                'combo_purchase', 'combo_sale_decide'} else '')
        if section and not unrestricted(date_policy, section):
            original = {**{key: value for key, value in original.items()
                           if key in {'id', 'at', 'business_date', 'actor', 'action'}},
                        'detail': {'summary': 'Nội dung cần quyền xem ngày hóa đơn tương ứng.'}}
        events.append(original)
    result['audit'] = events

    backups = []
    for original in result['backups']:
        snapshot = original.get('snapshot')
        if isinstance(snapshot, dict):
            snapshot = {section: filter_rows(snapshot.get(section, []), section, date_policy, now, requests)
                        for section in ('pending', 'invoices')}
            original = {**original, 'snapshot': snapshot}
        elif not (unrestricted(date_policy, 'pending') and unrestricted(date_policy, 'invoices')):
            original = {**original, 'bill_numbers': []}
        backups.append(original)
    result['backups'] = backups
    return result
