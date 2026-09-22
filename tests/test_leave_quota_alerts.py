from datetime import date
from types import SimpleNamespace
from contextlib import contextmanager
from fastapi import FastAPI
from fastapi.testclient import TestClient
import vera_leave_quota_alerts as alerts


def row(day, days=1, reason='Nghỉ CÓ phép', kind='Có phép', employee='Vy'):
    return dict(leave_date=date.fromisoformat(day),calculated_days=days,leave_reason=reason,leave_type=kind,employee_name=employee)


def test_strict_thresholds_half_days_and_month_employee_isolation():
    rows = [row(f'2026-09-{i:02}', .5) for i in range(1,11)]
    assert alerts.summarize(rows) == []
    rows += [row('2026-09-11', .5),row('2026-10-01'),row('2026-09-01',employee='Other')]
    result = alerts.summarize(rows)
    assert len(result) == 1
    assert result[0]['days'] == 5.5
    assert result[0]['exceeded'] == ['days']


def test_weekends_only_group3_unique_dates_and_generated_zero_day_records():
    rows = [row(d, 0, 'Đi trễ CUỐI TUẦN CÓ phép') for d in ['2026-09-05','2026-09-06']]
    rows += [row('2026-09-05',0,'Về sớm CUỐI TUẦN CÓ phép'),row('2026-09-12',0,'Quay video')]
    assert alerts.summarize(rows) == []
    rows += [row('2026-09-12',0,'Nghỉ CUỐI TUẦN CÓ phép')]
    rows += [row('2026-09-14',0,'Đi trễ PHÁT SINH','Phát sinh') for _ in range(3)]
    result = alerts.summarize(rows)[0]
    assert result['weekends'] == result['generated'] == 3
    assert result['exceeded'] == ['weekends','generated']
    assert alerts.fingerprint(result) == alerts.fingerprint({**result,'employee':'vy'})
    assert alerts.fingerprint(result) != alerts.fingerprint({**result,'generated':4})


def test_admin_api_whole_months_validation_and_no_db_for_forbidden():
    calls = []
    class Conn:
        def execute(self, sql, params):
            calls.append(params)
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: []))
    class Engine:
        @contextmanager
        def connect(self):
            yield Conn()
    role = ['nhanvien']
    app = FastAPI()
    alerts.install(app, engine_instance=lambda: Engine(), current_identity=lambda: SimpleNamespace(role=role[0]), identity_type=object)
    client = TestClient(app)
    url = '/v2/leave/quota-check?start=2026-09-15&end=2026-10-02'
    assert client.get(url).status_code == 403
    assert calls == []
    role[0]='admin'
    response=client.get(url)
    assert response.status_code == 200
    assert calls == [{'start':date(2026,9,1),'end':date(2026,10,31)}]
    assert client.get('/v2/leave/quota-check?start=2026-09-15&end=2026-08-02').status_code == 400
    assert client.get('/v2/leave/quota-check?start=2025-09-15&end=2026-09-02').status_code == 400


def test_delivery_retries_failed_device_without_holding_connection(monkeypatch):
    state = {'open':False,'sent':set(),'attempts':[]}
    item = {'employee':'Vy','month':'2026-09','days':6.0,'weekends':0,'generated':0,'exceeded':['days']}
    class Result:
        def __init__(self, rows=()): self.rows=rows
        def mappings(self): return self.rows
    class Conn:
        def execute(self, sql, params=None):
            sql=str(sql)
            if 'WITH candidates AS' in sql:
                assert "lower(btrim(p.role))='admin'" in sql
                assert 'FOR UPDATE OF d SKIP LOCKED' in sql
                return Result([dict(fingerprint='fp',subscription_id=device,payload=item) for device in ['a','b'] if device not in state['sent']])
            if 'UPDATE vera_leave_quota_delivery SET' in sql:
                if params['ok']: state['sent'].add(params['subscription_id'])
            return Result()
    class Engine:
        @contextmanager
        def begin(self):
            assert not state['open']
            state['open']=True
            try: yield Conn()
            finally: state['open']=False
    def send(delivery,*args):
        assert not state['open']
        device=delivery['subscription_id']
        state['attempts'].append(device)
        return (device=='a' or state['attempts'].count('b')>1,503,'')
    monkeypatch.setattr(alerts,'ensure_schema',lambda c:None)
    monkeypatch.setattr(alerts.settings,'is_enabled',lambda *args:True)
    monkeypatch.setattr(alerts,'_vault_secret',lambda *args:'key')
    monkeypatch.setattr(alerts,'_send',send)
    alerts.deliver(Engine())
    assert state['sent']=={'a'}
    alerts.deliver(Engine())
    assert state['attempts']==['a','b','b']
    assert state['sent']=={'a','b'}


def test_quota_permission_is_enforced_before_report_and_can_be_revoked(monkeypatch):
    from fastapi import HTTPException
    from vera_web_v2_permissions import FEATURES, permission_closure, DEFAULT_ROLE_FEATURES
    assert FEATURES['leave_quota_check'] == 'Kiểm tra vượt hạn mức'
    assert 'leave' in permission_closure({'leave_quota_check'})
    assert 'leave_quota_check' not in DEFAULT_ROLE_FEATURES['nhanvien']
    state = {'allowed': False, 'reads': 0}
    class Engine:
        @contextmanager
        def connect(self):
            yield object()
    def authorize(conn, ident, feature):
        assert feature == 'leave_quota_check'
        if not state['allowed']: raise HTTPException(403, 'Denied')
    def report(*args):
        state['reads'] += 1
        return []
    monkeypatch.setattr(alerts, 'read_report', report)
    app = FastAPI()
    alerts.install(app, engine_instance=Engine, current_identity=lambda: SimpleNamespace(role='nhanvien'), identity_type=object, require_feature=authorize)
    client = TestClient(app)
    url = '/v2/leave/quota-check?start=2026-09-01&end=2026-09-30'
    assert client.get(url).status_code == 403
    assert state['reads'] == 0
    state['allowed'] = True
    assert client.get(url).status_code == 200
    state['allowed'] = False
    assert client.get(url).status_code == 403
    assert state['reads'] == 1


def test_layout_destinations_reject_locked_targets_and_cycles():
    from fastapi import HTTPException
    from vera_web_v2_ui_layout import LayoutItem, REGISTRY, validate_items
    import pytest
    groups = [key for key, value in REGISTRY.items() if value.get('group') and not value.get('locked')]
    first, second = groups[:2]
    assert validate_items({first: LayoutItem(move_to=second)})[first]['move_to'] == second
    with pytest.raises(HTTPException):
        validate_items({first: LayoutItem(move_to=second), second: LayoutItem(move_to=first)})
    with pytest.raises(HTTPException):
        validate_items({first: LayoutItem(move_to='u-missing')})
