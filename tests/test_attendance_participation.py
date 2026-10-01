from copy import deepcopy
from datetime import date, datetime
from types import SimpleNamespace
import unicodedata

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

import vera_attendance_participation as policy
import vera_facegate_runtime as runtime
import vera_web_v2_department_payroll as department
import vera_web_v2_payroll as payroll
from test_facegate_runtime import facegate, record, evidence, DAY

PENDING_ENROLLMENT = ['Cậu Tưởng', 'Nguyễn Thị Sen', 'Nguyễn Thị Thu Hiền', 'Ngô Sĩ Đạt', 'Vũ Tân']


@pytest.mark.parametrize('username', ['admin', 'akamen', 'letan', 'Ms Tuyết'])
def test_all_accounts_resume_october_without_rewriting_september(username):
    rows = [{'username': username}]
    assert policy.suspended(username, date(2026, 9, 30))
    assert not policy.suspended(username, date(2026, 10, 1))
    assert policy.eligible(rows, date(2026, 10, 1), date(2026, 10, 31),
                           key='username') == rows
    policy.require_payroll_participants(rows, date(2026, 10, 1),
                                        date(2026, 10, 31), key='username')
    assert policy.preserved_payroll(rows, date(2026, 10, 1),
                                   date(2026, 10, 31), key='username') == []
    assert policy.suspended(username, date(2026, 9, 1), date(2026, 9, 30))
    assert policy.preserved_payroll(rows, date(2026, 9, 1),
                                   date(2026, 9, 30), key='username') == rows
    assert policy.status(date(2026, 10, 1))['excluded_usernames'] == []
    assert policy.status(date(2026, 10, 1))['excluded_employee_count'] == 0


def test_resumed_accounts_reappear_in_attendance_and_alerts(monkeypatch, facegate):
    users = ['admin', 'akamen', 'letan', 'Ms Tuyết']
    rows = [{**record(), 'employee_name': username, 'date': '01/10/2026',
             'check_out': ''} for username in users]
    result = runtime.annotate(rows, evidence())
    assert {row['employee_name'] for row in result} == set(users)
    assert all(row['attendance_pending'] for row in result)
    monkeypatch.setattr(runtime.fg, 'project_evidence', lambda *_: {
        'issues': [], 'index': {i: {'username': name} for i, name in enumerate(users)}})
    assert runtime.alert_eligible_users(object(), date(2026, 10, 1)) == set(users)


@pytest.mark.parametrize('username', ['admin', 'akamen', 'letan', 'Ms Tuyết'])
def test_effective_date_exact_account_and_resumption(monkeypatch, username):
    assert not policy.suspended(username, date(2026, 9, 28))
    assert policy.suspended(username.upper(), DAY)
    assert policy.suspended(unicodedata.normalize('NFD', username), DAY)
    assert policy.suspended(username, date(2026, 9, 16), date(2026, 9, 30))
    assert not policy.suspended(username + ' 2', DAY)
    monkeypatch.setattr(policy, 'SUSPENSIONS', ({'username': username,
        'effective_from': DAY, 'effective_until': date(2026, 10, 2)},))
    assert policy.suspended(username, date(2026, 10, 1))
    assert not policy.suspended(username, date(2026, 10, 2))
    assert policy.suspended(username, DAY), 'resumption must not rewrite history'


def test_only_four_accounts_removed_and_unregistered_staff_stay_pending(facegate):
    users = policy.status(DAY)['excluded_usernames'] + PENDING_ENROLLMENT + ['Gia Anh']
    rows = [{**record(), 'employee_name': username, 'check_out': ''} for username in users]
    original = deepcopy(rows)
    data = evidence()
    before = deepcopy(data)
    result = runtime.annotate(rows, data)
    assert {r['employee_name'] for r in result} == set(PENDING_ENROLLMENT + ['Gia Anh'])
    assert all(r['attendance_pending'] and not r['payable_minutes_verified'] for r in result)
    assert all('unmapped_employee' in r['attendance_pending_reasons'] for r in result)
    assert data == before
    assert rows[:4] == original[:4], 'suspension must not rewrite raw/excluded records'
    historical = [{**row, 'date': '28/09/2026'} for row in original[:4]]
    assert len(runtime.annotate(historical, data)) == 4


def test_inspection_reports_policy_without_writes(monkeypatch):
    import vera_attendance_source as source
    from vera_facegate_cutover import inspect
    monkeypatch.setattr(source, 'health', lambda _: {'source': 'facegate'})
    monkeypatch.setattr(runtime, 'records', lambda *_: [])
    result = inspect(object(), DAY)
    assert result['excluded_employee_count'] == 4
    assert result['excluded_usernames'] == ['admin', 'akamen', 'letan', 'Ms Tuyết']
    assert result['employee_count'] == 0 and result['pending_employee_count'] == 0


def test_alert_eligibility_does_not_alert_suspended_accounts(monkeypatch):
    users = ['admin', 'letan', 'Ms Tuyết', 'Gia Anh']
    monkeypatch.setattr(runtime.fg, 'project_evidence', lambda *_: {
        'issues': [], 'index': {i: {'username': name} for i, name in enumerate(users)}})
    assert runtime.alert_eligible_users(object(), DAY) == {'Gia Anh'}


@pytest.mark.parametrize('calculation_source', ['attendance', 'schedule'])
def test_finalization_rejects_stale_client_rows_even_schedule_source(monkeypatch, facegate, calculation_source):
    monkeypatch.setattr(department.attendance, '_records', lambda *_: pytest.fail('must reject before attendance read'))
    for username in policy.status(DAY)['excluded_usernames']:
        with pytest.raises(HTTPException) as error:
            department._require_complete_attendance(object(), '2026-09',
                [{'employee_username': username, 'calculation_source': calculation_source}], str)
        assert error.value.status_code == 409
    department._require_complete_attendance(object(), '2026-08',
        [{'employee_username': 'Ms Tuyết'}], str)


def test_tip_draft_validates_canonical_identity_and_keeps_history(monkeypatch):
    employee = {'username': 'Ms Tuyết', 'full_name': 'Tuyết', 'email': '',
                'bank_account': '', 'bank_name': ''}
    norm = lambda value: unicodedata.normalize('NFD', str(value)).casefold()
    monkeypatch.setattr(payroll, '_employee_catalog', lambda *_: {norm('Ms Tuyết'): employee})
    supplied = [{'Tên Hệ thống': 'MS TUYẾT', 'Tiền Lương': 12345}]
    before = deepcopy(supplied)
    with pytest.raises(HTTPException) as error:
        payroll._clean_draft_rows(object(), supplied, norm, period=(DAY, DAY))
    assert error.value.status_code == 409
    old = payroll._clean_draft_rows(object(), supplied, norm,
                                    period=(date(2026, 9, 1), date(2026, 9, 15)))
    assert old[0]['Tiền Lương'] == 12345 and supplied == before


@pytest.mark.parametrize('entry', ['detail', 'browser_login', 'browser_recalculate', 'original_browser_login', 'json_api'])
def test_direct_legacy_entrypoints_cannot_contact_timesoft(facegate, entry):
    import timesoft_detailed_checkin as detail
    import timesoft_recalculate_checkin as browser
    import timesoft_sync_job as sync
    with pytest.raises(RuntimeError, match='timesoft_disabled_by_facegate_cutover'):
        if entry == 'detail':
            detail.fetch_detailed_checkin(object(), object(), DAY)
        elif entry == 'browser_login':
            browser._login_without_forced_reverify(object(), object())
        elif entry == 'browser_recalculate':
            browser.recalculate_today(object(), object())
        elif entry == 'original_browser_login':
            sync._login_with_playwright(object(), 'unused')
        else:
            sync.post_json(object(), '/unused', '/unused', {})


def test_retired_payroll_download_rejects_before_reading_old_snapshots(monkeypatch, facegate):
    import vera_web_v2_payroll_timesoft_auto as auto
    class Connection:
        def __enter__(self): return self
        def __exit__(self, *args): pass
    ident = SimpleNamespace(allowed=True)
    def require(conn, identity, feature):
        if not identity.allowed: raise HTTPException(403, 'Forbidden')
    monkeypatch.setattr(auto, '_canonical_tip_rows', lambda *_: pytest.fail('stale TimeSoft snapshots read'))
    app = FastAPI()
    auto.install_payroll_timesoft_auto_routes(app,
        engine_instance=lambda: SimpleNamespace(connect=Connection),
        current_identity=lambda: ident, require_feature=require, identity_type=SimpleNamespace, norm=str)
    with TestClient(app) as client:
        assert client.get('/v2/payroll-timesoft-auto/health').json()['enabled'] is False
        assert client.get('/v2/payroll/timesoft-source.xlsx?month=2026-09&period_no=2').status_code == 410
        ident.allowed = False
        assert client.get('/v2/payroll/timesoft-source.xlsx?month=2026-09&period_no=2').status_code == 403
