from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

import vera_hc_rules as hc
from test_notification_schema_locking import database

DAY = date(2026, 10, 5)
def at(clock, day=DAY):
    return datetime.fromisoformat(f'{day}T{clock}:00+07:00')

CONFIG = dict(calculation_mode='hourly', rate_ca1=30000, rate_ca2_before_22=40000, rate_ca2_after_22=60000)

def fixture(arrival='09:15'):
    row = dict(employee_username='Lan', employee_role='locker', hc_department='locker', department='locker',
               shift_code='Ca 1', main_start='09:00', main_end='17:00', overtime_shift='', ot_start='', ot_end='')
    current = {'revision': 1, 'departments': {'locker': {'enabled': True, 'enabled_since': at('08:00').isoformat()}}}
    data = dict(index={'1': {'username': 'Lan'}}, rows=[], issues=[], events=[], syncs=[])
    if arrival:
        data['rows'] = [dict(EmployeeName='Lan', WorkDateStr='05/10/2026', _vera_checkin_at=at(arrival).isoformat())]
    data['syncs'] = [dict(work_date=DAY, last_synced_at=at('18:00'), last_observed_count=0)]
    return row, data, current


def test_late_money_and_monthly_basic_salary_excludes_allowances():
    assert hc.penalty(CONFIG, at('09:00'), at('09:15'), 'Ca 1') == 15000
    monthly = dict(calculation_mode='monthly', default_base_salary=6240000, standard_month_days=26,
                   standard_day_hours=8, responsibility=5000000, full_allowance=2000000)
    assert hc.penalty(monthly, at('09:00'), at('09:15'), 'Ca 1') == 15000
    assert hc.penalty(monthly, at('09:00'), at('17:00'), 'Ca 1') == 480000


def test_overnight_rate_matches_department_payroll_cutoff():
    assert hc.penalty(CONFIG, at('21:00'), at('02:00', DAY+timedelta(days=1)), 'Ca 2') == 560000
    assert hc.interval(DAY, '09:00', '09:00') is None


@pytest.mark.parametrize('config', [dict(calculation_mode='tip'), dict(CONFIG, rate_ca1=0), dict(CONFIG, rate_ca1=-1), dict(CONFIG, rate_ca1='NaN')])
def test_no_fabricated_wage_when_configuration_invalid(config):
    with pytest.raises(ValueError):
        hc.penalty(config, at('09:00'), at('09:15'), 'Ca 1')


def test_earliest_arrival_and_earlier_overtime_are_respected():
    row, data, current = fixture('09:15')
    decision = hc.candidate(row, DAY, data, current, at('18:00'), [])
    assert decision['minutes'] == 15
    data['rows'].append(dict(EmployeeName='Lan', WorkDateStr='05/10/2026', _vera_checkin_at=at('08:55').isoformat()))
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None
    row.update(main_start='13:00', main_end='23:00', shift_code='Ca 2', overtime_shift='TC Ca 1', ot_start='09:00', ot_end='13:00')
    data['rows'] = data['rows'][:1]
    decision = hc.candidate(row, DAY, data, current, at('18:00'), [])
    assert decision['start'] == at('09:00') and decision['shift'] == 'Ca 1'


def test_absence_uses_entire_main_shift_without_overtime_only_after_complete_sync():
    row, data, current = fixture(None)
    row.update(main_start='13:00', main_end='23:00', shift_code='Ca 2', overtime_shift='TC Ca 1', ot_start='09:00', ot_end='13:00')
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None
    data['syncs'][0]['last_synced_at'] = at('23:30')
    decision = hc.candidate(row, DAY, data, current, at('23:30'), [])
    assert decision['start'] == at('13:00') and decision['end'] == at('23:00')
    assert hc.penalty(CONFIG, decision['start'], decision['end'], decision['shift']) == 840000
    data['syncs'][0]['last_observed_count'] = 1
    assert hc.candidate(row, DAY, data, current, at('23:30'), []) is None


@pytest.mark.parametrize('role', sorted(hc.EXCLUDED))
def test_exclusions_cannot_be_bypassed_by_department_assignment(role):
    row, data, current = fixture()
    row['employee_role'] = role
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None


def test_disabled_activation_cutoff_identity_and_leave_safeguards():
    row, data, current = fixture()
    for leaves in ([dict(leave_reason='Nghỉ có phép', penalty=0)], [dict(leave_reason='Nghỉ KHÔNG phép', penalty=50000)]):
        assert hc.candidate(row, DAY, data, current, at('18:00'), leaves) is None
    current['departments']['locker']['enabled'] = False
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None
    current['departments']['locker'].update(enabled=True, enabled_since=at('09:01').isoformat())
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None
    current['departments']['locker']['enabled_since'] = at('08:00').isoformat()
    data['index'] = {}
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None


def test_mapped_scan_outside_window_is_never_absence():
    row, data, current = fixture(None)
    data['issues'] = [dict(username='Lan', reason='no_vera_shift')]
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None


def setup_tables(conn):
    conn.execute(text('''CREATE TABLE vera_app_setting(category text,setting_key text,value_json jsonb,revision integer,
        source text,updated_by text,created_at timestamptz,updated_at timestamptz,PRIMARY KEY(category,setting_key));
        CREATE TABLE leave_records(source_sheet_id text,source_row integer,leave_date date,employee_name text,leave_reason text,
        leave_type text,detail text,calculated_days numeric,accumulated_leave numeric,penalty numeric,update_date text,
        update_time text,updated_by text,weekday_label text,payload jsonb,record_uid text,created_at timestamptz,updated_at timestamptz);'''))
    hc.ensure_schema(conn)


def test_atomic_deduplication_and_payroll_inclusion(database, monkeypatch):
    import vera_notification_delivery as delivery
    import vera_web_v2_department_payroll as payroll
    with database.begin() as conn:
        setup_tables(conn)
        conn.execute(text('CREATE TABLE test_outbox(tag text PRIMARY KEY)'))
    def enqueue(conn, kind, payload, event_key):
        assert kind == 'auto_penalty'
        conn.execute(text('INSERT INTO test_outbox VALUES(:tag)'), {'tag': event_key})
    monkeypatch.setattr(delivery, 'enqueue', enqueue)
    row, data, current = fixture()
    decision = hc.candidate(row, DAY, data, current, at('18:00'), [])
    with database.begin() as conn:
        assert hc.write_penalty(conn, row, DAY, decision, 15000, 1, CONFIG)
        assert not hc.write_penalty(conn, row, DAY, decision, 15000, 1, CONFIG)
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM test_outbox')).scalar() == 1
        assert conn.execute(text('SELECT sum(calculated_days) FROM leave_records')).scalar() == 0
        violation, late = payroll._penalty_maps(conn, DAY, DAY, hc._norm)
        assert late == {'lan': 15000} and not violation
        conn.execute(text('DELETE FROM leave_records'))
        assert not hc.write_penalty(conn, row, DAY, decision, 15000, 1, CONFIG)
    def fail(*a, **k):
        raise RuntimeError('outbox failed')
    monkeypatch.setattr(delivery, 'enqueue', fail)
    with pytest.raises(RuntimeError):
        with database.begin() as conn:
            hc.write_penalty(conn, row, DAY+timedelta(days=1), decision, 15000, 1, CONFIG)
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_hc_penalty_event')).scalar() == 1
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar() == 0


def test_routes_department_switches_revision_and_admin_only(database, monkeypatch):
    with database.begin() as conn:
        setup_tables(conn)
    monkeypatch.setattr(hc, 'definitions', lambda conn: {'locker': {'name': 'Locker', 'salary_mode': 'hourly'}, 'letan': {'name': 'Lễ tân', 'salary_mode': 'hourly'}})
    ident = SimpleNamespace(role='admin', employee_username='admin')
    app = FastAPI()
    def identity():
        return ident
    grants = []
    hc.install_routes(app, engine_instance=lambda: database, current_identity=identity,
                      require_feature=lambda conn, user, key: grants.append(key), identity_type=SimpleNamespace)
    client = TestClient(app)
    assert all(not d['enabled'] for d in client.get('/v2/rules/hc').json()['departments'])
    result = client.put('/v2/rules/hc/locker', json={'enabled': True, 'expected_revision': 0})
    assert result.status_code == 200
    assert [d['enabled'] for d in result.json()['departments']] == [True, False]
    assert client.put('/v2/rules/hc/letan', json={'enabled': True, 'expected_revision': 0}).status_code == 409
    assert client.put('/v2/rules/hc/admin', json={'enabled': True, 'expected_revision': 1}).status_code == 400
    ident.role = 'giamdoc'
    assert client.put('/v2/rules/hc/locker', json={'enabled': False, 'expected_revision': 1}).status_code == 403
    assert 'official_rules_view' in grants and 'official_rules_edit' in grants


def test_fresh_archive_is_required_and_ambiguous_or_stale_evidence_blocks_all_writes():
    row, data, current = fixture()
    data['events'] = [{'occurred_at': at('09:15').isoformat()}]
    data['syncs'][0].update(last_synced_at=at('09:16'), last_observed_count=1)
    assert hc.fresh_evidence(data, DAY, at('09:17'))
    assert not hc.fresh_evidence(data, DAY, at('09:22'))
    data['issues'] = [{'reason': 'unmapped_reference'}]
    assert not hc.fresh_evidence(data, DAY, at('09:17'))
    data['issues'] = []
    data['syncs'][0]['last_observed_count'] = 2
    assert not hc.fresh_evidence(data, DAY, at('09:17'))
    data['syncs'][0]['last_synced_at'] = 'invalid'
    assert not hc.fresh_evidence(data, DAY, at('09:17'))


def test_disabled_worker_does_not_read_evidence_or_create_schema(monkeypatch):
    class Connection:
        def execute(self, statement, parameters=None):
            assert 'pg_advisory_xact_lock' in str(statement)
    monkeypatch.setattr(hc, 'policy', lambda conn: {'revision': 0, 'departments': {}})
    assert hc.process(Connection(), now=at('18:00')) == {'added': 0, 'pending': 0, 'reason': 'disabled'}


def test_schedule_query_uses_hr_assignment_and_vera_shift_definitions(database):
    with database.begin() as conn:
        setup_tables(conn)
        conn.execute(text('''CREATE TABLE employees(username text,role text,payload jsonb);
            CREATE TABLE vera_work_schedule(work_date date,employee_username text,department text,shift_code text,
            start_time text,end_time text,overtime_shift text,overtime_start_time text,overtime_end_time text);
            CREATE TABLE vera_work_shift_definition(department text,shift_code text,start_time text,end_time text);
            INSERT INTO employees VALUES ('Lan','support','{}');
            INSERT INTO vera_app_setting(category,setting_key,value_json,revision) VALUES
              ('payroll','hr_registry','{"assignments":{"Lan":"locker"}}',1);
            INSERT INTO vera_work_schedule VALUES ('2026-10-05','Lan','locker','Ca 2','','','TC Ca 1','','');
            INSERT INTO vera_work_shift_definition VALUES ('locker','Ca 1','09:00','13:00'),('locker','Ca 2','13:00','23:00');'''))
        row = hc.scheduled_rows(conn, DAY)[0]
        assert row['hc_department'] == 'locker' and row['employee_role'] == 'support'
        assert (row['main_start'], row['main_end'], row['ot_start'], row['ot_end']) == ('13:00','23:00','09:00','13:00')


def test_late_crossing_earlier_overtime_and_main_prices_each_rate_once_without_gaps():
    row, data, current = fixture('13:15')
    row.update(main_start='13:00', main_end='23:00', shift_code='Ca 2', overtime_shift='TC Ca 1', ot_start='09:00', ot_end='13:00')
    decision = hc.candidate(row, DAY, data, current, at('18:00'), [])
    assert hc.decision_penalty(CONFIG, row, DAY, decision) == 260000
    assert [s['shift'] for s in decision['wage_segments']] == ['Ca 1', 'Ca 2']
    row['ot_end'] = '11:00'
    assert hc.decision_penalty(CONFIG, row, DAY, decision) == 140000
    row['ot_end'] = '15:00'
    assert hc.decision_penalty(CONFIG, row, DAY, decision) == 260000


def test_activation_after_earlier_overtime_started_does_not_backfill_it():
    row, data, current = fixture('13:15')
    row.update(main_start='13:00', main_end='23:00', shift_code='Ca 2', overtime_shift='TC Ca 1', ot_start='09:00', ot_end='13:00')
    current['departments']['locker']['enabled_since'] = at('10:00').isoformat()
    assert hc.candidate(row, DAY, data, current, at('18:00'), []) is None
