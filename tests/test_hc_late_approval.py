from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal
import json
from types import SimpleNamespace

from fastapi import FastAPI, HTTPException
from pydantic import ValidationError
import pytest

import vera_hc_late_approval as approval
import vera_web_v2_work_schedule as schedule

DAY = date(2026, 10, 6)
NOW = datetime.fromisoformat('2026-10-06T12:00:00+07:00')
BASIS = {
    'kind': 'late', 'start': '2026-10-06T09:00:00+07:00', 'end': '2026-10-06T09:15:00+07:00', 'minutes': 15,
    'rule': {'mode': 'multiplier', 'value': 2},
    'config': {'calculation_mode': 'hourly', 'rate_ca1': 30000},
    'wage_segments': [{'start': '2026-10-06T09:00:00+07:00', 'end': '2026-10-06T09:15:00+07:00', 'shift': 'Ca 1'}],
}


def fixture():
    row = dict(record_uid='uid', employee_name='Lan', leave_date=DAY, source_sheet_id=approval.SOURCE,
               updated_at=NOW, penalty=15000, payload={'hc_basis': deepcopy(BASIS)}, detail='Original minutes/evidence')
    event = dict(id=123, work_date=DAY, employee_name='Lan', kind='late', amount=15000,
                 basis=deepcopy(BASIS), leave_record_uid='uid')
    return row, event


class Result:
    def __init__(self, value=None, rows=None): self.value, self.rows = value, rows or []
    def scalar(self): return self.value
    def mappings(self): return self
    def first(self): return self.rows[0] if self.rows else None
    def all(self): return self.rows


class Connection:
    def __init__(self, row, event, histories=None):
        self.row, self.event, self.histories, self.writes, self.calls = row, event, histories or [], [], []
    def execute(self, statement, params=None):
        sql = str(statement); self.calls.append((sql, params))
        if 'to_regclass' in sql: return Result('vera_hc_penalty_event')
        if 'SELECT * FROM leave_records' in sql: return Result(rows=[self.row])
        if 'SELECT * FROM vera_hc_penalty_event' in sql: return Result(rows=[self.event] if self.event else [])
        if 'SELECT value_json' in sql: return Result(rows=[{'value_json': self.histories}])
        if 'UPDATE leave_records' in sql: self.writes.append(params)
        return Result()


def test_exact_money_uses_immutable_basis_not_half_of_rounded_fine():
    basis = deepcopy(BASIS)
    basis['config']['rate_ca1'] = Decimal('30002')
    assert approval.price_basis(basis, DAY) == {False: 15001, True: 7501}
    basis['config'] = dict(calculation_mode='monthly', default_base_salary=6240000,
                           standard_month_days=26, standard_day_hours=8, full_allowance=5000000)
    assert approval.price_basis(basis, DAY) == {False: 15000, True: 7500}


def test_seconds_and_midnight_cutoff_are_preserved():
    basis = deepcopy(BASIS)
    basis.update(start='2026-10-06T21:59:30+07:00', end='2026-10-07T00:00:30+07:00')
    basis['config'] = dict(calculation_mode='hourly', rate_ca2_before_22=36000, rate_ca2_after_22=72000)
    basis['wage_segments'] = [dict(start=basis['start'], end=basis['end'], shift='Ca 2')]
    assert approval.price_basis(basis, DAY) == {False: 289800, True: 144900}


@pytest.mark.parametrize('change', [
    {'kind': 'absence'}, {'kind': 'early_leave'}, {'kind': 'missing_checkout'},
    {'rule': {'mode': 'fixed', 'value': 15000}}, {'rule': {'mode': 'multiplier', 'value': 3}},
    {'wage_segments': []}, {'config': {'calculation_mode': 'hourly', 'rate_ca1': 0}},
    {'start': '2026-10-06T09:00:00'}, {'end': '2026-10-06T08:00:00+07:00'},
])
def test_other_violations_custom_rules_and_missing_evidence_cannot_be_repriced(change):
    with pytest.raises((ValueError, KeyError)):
        approval.price_basis({**deepcopy(BASIS), **change}, DAY)


def test_overlap_or_out_of_interval_segments_rejected():
    basis = deepcopy(BASIS); basis['wage_segments'] *= 2
    with pytest.raises(ValueError): approval.price_basis(basis, DAY)
    basis['wage_segments'] = [dict(BASIS['wage_segments'][0], start='2026-10-06T08:59:00+07:00')]
    with pytest.raises(ValueError): approval.price_basis(basis, DAY)


def test_approval_unapproval_roundtrip_preserves_original_event_and_evidence():
    row, event = fixture(); before = deepcopy(event); conn = Connection(row, event)
    payload, amount = approval.apply(conn, row, True, 'admin', NOW)
    assert amount == 7500 and payload[approval.KEY]['approved'] is True
    assert payload['hc_basis'] == BASIS and row['detail'] == 'Original minutes/evidence' and event == before
    assert payload['schedule_violation_changes'][-1]['before']['amount'] == '15000'
    assert payload['schedule_violation_changes'][-1]['actor'] == 'admin'
    row.update(payload=payload, penalty=amount)
    # The same persisted state never halves the previous amount again.
    payload, amount = approval.apply(conn, row, True, 'admin', NOW)
    assert amount == 7500
    row.update(payload=payload, penalty=amount)
    payload, amount = approval.apply(conn, row, False, 'admin', NOW)
    assert amount == 15000 and payload[approval.KEY]['multiplier'] == 2
    assert len(payload['schedule_violation_changes']) == 3
    assert event == before


def test_metadata_avoids_private_wage_config_and_manual_adjustments():
    row, _ = fixture(); result = approval.metadata(row)
    assert result['hc_late_approval_eligible'] and result['hc_late_minutes'] == 15
    assert 'config' not in result and 'payload' not in result
    assert not approval.metadata(dict(row, penalty=12000))['hc_late_approval_eligible']
    assert approval.metadata(dict(row, source_sheet_id='manual')) == {}
    row['payload']['__schedule_violation_deleted'] = True
    assert not approval.metadata(row)['hc_late_approval_eligible']


@pytest.mark.parametrize('change', [{'kind': 'absence'}, {'amount': 123}, {'employee_name': 'Other'}, {'basis': {}}])
def test_unmatched_original_event_fails_closed(change):
    row, event = fixture(); event.update(change)
    with pytest.raises(HTTPException) as exc: approval.apply(Connection(row, event), row, True, 'admin', NOW)
    assert exc.value.status_code == 409


@pytest.mark.parametrize('key', ['combined', 'department'])
def test_finalized_employee_month_blocks_changes(key):
    row, event = fixture()
    entries = [dict(month='2026-10', rows=[dict(employee_username=' lan ')])]
    conn = Connection(row, event, entries)
    with pytest.raises(HTTPException) as exc: approval.apply(conn, row, True, 'admin', NOW)
    assert exc.value.status_code == 409 and not conn.writes
    assert event['amount'] == 15000


def test_other_employee_or_month_snapshot_does_not_block():
    row, event = fixture()
    entries = [dict(month='2026-09', rows=[dict(employee_username='Lan')]), dict(month='2026-10', rows=[dict(employee_username='Other')])]
    assert approval.apply(Connection(row, event, entries), row, True, 'admin', NOW)[1] == 7500


def test_endpoint_preserves_admin_only_gate_before_any_database():
    app = FastAPI()
    schedule.install_work_schedule_routes(app, engine_instance=lambda: pytest.fail('no DB for denied role'),
                                         current_identity=lambda: None, feature_allowed=lambda *args: True)
    endpoint = next(r.endpoint for r in app.routes if r.path.endswith('/{violation_id}/late-approval'))
    body = schedule.ScheduleLateApproval(department='support', expected_updated_at=NOW, approved=True)
    for role in ['quanly', 'letan', 'support', 'giamdoc']:
        with pytest.raises(HTTPException) as exc: endpoint('uid', body, SimpleNamespace(role=role))
        assert exc.value.status_code == 403
    with pytest.raises(ValidationError): schedule.ScheduleLateApproval(department='support', expected_updated_at=NOW, approved='false')


def test_mutation_cas_scope_and_audit(monkeypatch):
    row, event = fixture(); conn = Connection(row, event)
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username': 'Lan'}])
    body = schedule.ScheduleLateApproval(department='support', expected_updated_at=NOW, approved=True)
    actor = SimpleNamespace(employee_username='Admin', role='admin')
    assert schedule._approve_schedule_late(conn, 'uid', body, actor)['amount'] == 7500
    assert len(conn.writes) == 1
    assert json.loads(conn.writes[0]['payload'])[approval.KEY]['actor'] == 'Admin'
    assert "pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))" in conn.calls[0][0]
    assert 'FOR UPDATE' in conn.calls[1][0]
    stale = body.model_copy(update={'expected_updated_at': NOW.replace(hour=11)})
    with pytest.raises(HTTPException) as exc: schedule._approve_schedule_late(conn, 'uid', stale, actor)
    assert exc.value.status_code == 409 and len(conn.writes) == 1
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username': 'Other'}])
    with pytest.raises(HTTPException) as exc: schedule._approve_schedule_late(conn, 'uid', body, actor)
    assert exc.value.status_code == 403 and len(conn.writes) == 1


from test_notification_schema_locking import database


def test_postgres_approval_recompute_cas_and_finalized_history(database, monkeypatch):
    from sqlalchemy import text
    import vera_hc_rules as hc
    import vera_notification_delivery as delivery
    from test_hc_rules import setup_tables
    monkeypatch.setattr(delivery, 'enqueue', lambda *args, **kwargs: None)
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username': 'Lan'}])
    scheduled = dict(employee_username='Lan', hc_department='support')
    decision = deepcopy(BASIS)
    decision.update(start=datetime.fromisoformat(BASIS['start']), end=datetime.fromisoformat(BASIS['end']))
    with database.begin() as conn:
        setup_tables(conn)
        assert hc.write_penalty(conn, scheduled, DAY, decision, 15000, 1, BASIS['config'])
        before = dict(conn.execute(text('SELECT * FROM vera_hc_penalty_event')).mappings().first())
        row = dict(conn.execute(text('SELECT * FROM leave_records')).mappings().first())
    actor = SimpleNamespace(employee_username='Admin', role='admin')
    body = schedule.ScheduleLateApproval(department='support', expected_updated_at=row['updated_at'], approved=True)
    with database.begin() as conn:
        assert schedule._approve_schedule_late(conn, row['record_uid'], body, actor)['amount'] == 7500
    with database.begin() as conn:
        saved = dict(conn.execute(text('SELECT * FROM leave_records')).mappings().first())
        assert saved['penalty'] == 7500 and saved['payload'][approval.KEY]['approved'] is True
        assert saved['detail'] == row['detail'] and saved['payload']['hc_basis'] == row['payload']['hc_basis']
        assert dict(conn.execute(text('SELECT * FROM vera_hc_penalty_event')).mappings().first()) == before
        assert not hc.write_penalty(conn, scheduled, DAY, decision, 15000, 1, BASIS['config'])
        assert conn.execute(text('SELECT penalty FROM leave_records')).scalar() == 7500
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            schedule._approve_schedule_late(conn, row['record_uid'], body, actor)
    assert exc.value.status_code == 409
    official = [{'month': '2026-10', 'rows': [{'employee_username': 'Lan', 'net_salary': 999999}]}]
    with database.begin() as conn:
        conn.execute(text("INSERT INTO vera_app_setting(category,setting_key,value_json,revision) VALUES('payroll','department_payroll_combined_history',CAST(:value AS jsonb),1)"), {'value': json.dumps(official)})
    with pytest.raises(HTTPException) as exc:
        with database.begin() as conn:
            schedule._approve_schedule_late(conn, row['record_uid'], body.model_copy(update={'approved':False,'expected_updated_at':saved['updated_at']}), actor)
    assert exc.value.status_code == 409
    with database.begin() as conn:
        assert conn.execute(text('SELECT penalty FROM leave_records')).scalar() == 7500
        assert conn.execute(text("SELECT value_json FROM vera_app_setting WHERE setting_key='department_payroll_combined_history'")).scalar() == official
        assert dict(conn.execute(text('SELECT * FROM vera_hc_penalty_event')).mappings().first()) == before


def test_postgres_approval_shares_finalization_lock(database, monkeypatch):
    from sqlalchemy import text
    from sqlalchemy.exc import DBAPIError
    import vera_hc_rules as hc
    import vera_notification_delivery as delivery
    from test_hc_rules import setup_tables
    monkeypatch.setattr(delivery, 'enqueue', lambda *args, **kwargs: None)
    monkeypatch.setattr(schedule, '_employee_catalog', lambda *args: [{'username': 'Lan'}])
    decision = deepcopy(BASIS)
    decision.update(start=datetime.fromisoformat(BASIS['start']), end=datetime.fromisoformat(BASIS['end']))
    with database.begin() as conn:
        setup_tables(conn)
        hc.write_penalty(conn, dict(employee_username='Lan', hc_department='support'), DAY, decision, 15000, 1, BASIS['config'])
        row = dict(conn.execute(text('SELECT * FROM leave_records')).mappings().first())
    with database.begin() as finalizer:
        finalizer.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
        with pytest.raises(DBAPIError):
            with database.begin() as editor:
                editor.execute(text("SET LOCAL lock_timeout='150ms'"))
                schedule._approve_schedule_late(editor, row['record_uid'],
                    schedule.ScheduleLateApproval(department='support', expected_updated_at=row['updated_at'], approved=True),
                    SimpleNamespace(employee_username='Admin', role='admin'))
    with database.begin() as conn:
        assert conn.execute(text('SELECT penalty FROM leave_records')).scalar() == 15000
        assert conn.execute(text("SELECT payload->'hc_late_approval' FROM leave_records")).scalar() is None


def test_missing_or_mismatched_approval_audit_is_not_eligible():
    row, event = fixture()
    row['penalty'] = 7500
    row['payload'][approval.KEY] = {'approved': True}
    assert not approval.metadata(row)['hc_late_approval_eligible']
    row['payload'][approval.KEY] = dict(version=1, approved=True, multiplier=1, actor='Admin', at=NOW.isoformat(), event_id=999)
    with pytest.raises(HTTPException) as exc: approval.apply(Connection(row, event), row, True, 'Admin', NOW)
    assert exc.value.status_code == 409


@pytest.mark.parametrize('history', ['broken', {'rows': []}, [None], [{'month': '2026-10', 'rows': None}]])
def test_unreadable_finalized_history_fails_closed(history):
    row, event = fixture()
    conn = Connection(row, event)
    conn.histories = history
    with pytest.raises(HTTPException) as exc: approval.apply(conn, row, True, 'Admin', NOW)
    assert exc.value.status_code == 409


def test_historical_hourly_after_midnight_custom_bucket_is_not_reinterpreted():
    basis = deepcopy(BASIS)
    basis.update(start='2026-10-07T01:30:00+07:00', end='2026-10-07T02:00:00+07:00')
    basis['config'] = dict(calculation_mode='hourly', rate_ca1=27000, rate_ca2_after_22=60000)
    basis['wage_segments'] = [dict(start=basis['start'], end=basis['end'], shift='Giờ làm')]
    original = deepcopy(basis)
    with pytest.raises(ValueError, match='historical_overnight_wage_bucket'):
        approval.price_basis(basis, DAY)
    assert basis == original
    basis['wage_segments'][0]['shift'] = 'Ca 2'
    assert approval.price_basis(basis, DAY) == {False: 60000, True: 30000}
    # Monthly basic wage has no Ca 1/Ca 2 bucket difference.
    basis['wage_segments'][0]['shift'] = 'Giờ làm'
    basis['config'] = dict(calculation_mode='monthly', default_base_salary=6240000, standard_month_days=26, standard_day_hours=8)
    assert approval.price_basis(basis, DAY) == {False: 30000, True: 15000}
