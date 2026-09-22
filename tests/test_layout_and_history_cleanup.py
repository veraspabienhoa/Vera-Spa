import json
from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from vera_web_v2_ui_layout import LayoutWrite, LayoutItem, install_ui_layout_routes, validate_items
from vera_web_v2_board_history_cleanup import HistoryFilter, HistoryDelete, install_board_history_cleanup

class App:
    def __init__(self): self.routes = {}
    def route(self, method, path):
        def register(fn): self.routes[method, path] = fn; return fn
        return register
    def get(self, path): return self.route('GET', path)
    def put(self, path): return self.route('PUT', path)
    def post(self, path): return self.route('POST', path)
    def delete(self, path): return self.route('DELETE', path)

class Conn:
    def __init__(self):
        self.row = {'value_json': {'desktop': {'l-original': {'width': 100}}, 'mobile': {}}, 'revision': 2}
        self.calls = []
    def execute(self, query, params=None):
        sql = str(query); self.calls.append((sql, params))
        if sql.startswith('INSERT INTO vera_app_setting'):
            self.row = {'value_json': json.loads(params['value']), 'revision': params['revision']}
        return self
    def mappings(self): return self
    def first(self): return self.row
    def one(self): return {'count': 7000, 'cutoff_id': 9500}
    def scalar_one(self): return 7000
    @contextmanager
    def begin(self): yield self


def fixture(install):
    app = App(); conn = Conn()
    install(app, engine_instance=lambda: conn, current_identity=lambda: None, identity_type=object)
    return app.routes, conn


def test_layout_admin_only_revision_and_separate_devices():
    routes, conn = fixture(install_ui_layout_routes)
    update = routes['PUT', '/v2/ui-layout']
    body = LayoutWrite(device='mobile', revision=2, items={'l-test': {'width': 80}})
    with pytest.raises(HTTPException) as denied:
        update(body, SimpleNamespace(role='nhanvien'))
    assert denied.value.status_code == 403
    assert not conn.calls
    admin = SimpleNamespace(role='admin', employee_username='Admin')
    result = update(body, admin)
    assert result['layout']['desktop'] == {'l-original': {'width': 100}}
    assert result['layout']['mobile'] == {'l-test': {'width': 80}}
    assert result['revision'] == 3
    with pytest.raises(HTTPException) as conflict:
        update(body, admin)
    assert conflict.value.status_code == 409
    assert routes['GET', '/v2/ui-layout'](SimpleNamespace(role='nhanvien')) == result


def test_layout_rejects_css_selectors_and_unbounded_sizes():
    with pytest.raises(HTTPException): validate_items({'body': LayoutItem(width=100)})
    with pytest.raises(HTTPException): validate_items({'l-valid': LayoutItem(parent='body{}')})
    with pytest.raises(ValidationError): LayoutItem(width=999999)
    with pytest.raises(ValidationError): LayoutItem(order=-1)


def test_history_cleanup_exact_scope_all_matching_rows_and_cutoff(monkeypatch):
    monkeypatch.setattr('vera_web_v2_board_history_cleanup.ensure_schema', lambda conn: None)
    routes, conn = fixture(install_board_history_cleanup)
    admin = SimpleNamespace(role='admin')
    scope = {'date_from': '2026-09-20', 'date_to': '2026-09-22', 'employee': ' Phương Vy '}
    preview = routes['POST', '/v2/live-tour/board-history/cleanup-preview'](HistoryFilter(**scope), admin)
    assert preview == {'count': 7000, 'cutoff_id': 9500}
    delete = routes['DELETE', '/v2/live-tour/board-history']
    body = HistoryDelete(**scope, cutoff_id=9500, confirm=True)
    assert delete(body, admin)['deleted'] == 7000
    sql, params = conn.calls[-1]
    assert 'DELETE FROM vera_live_tour_board_history' in sql
    assert 'id <= :cutoff_id' in sql and 'LIMIT' not in sql
    assert "Asia/Ho_Chi_Minh" in sql
    assert params['employee'] == 'Phương Vy'
    assert str(params['date_from']) == '2026-09-20'
    assert str(params['date_to']) == '2026-09-22'
    for ident, confirm in [(SimpleNamespace(role='letan'), True), (admin, False)]:
        before = len(conn.calls)
        with pytest.raises(HTTPException): delete(body.model_copy(update={'confirm': confirm}), ident)
        assert len(conn.calls) == before
    with pytest.raises(ValidationError): HistoryFilter(date_from='2026-09-23', date_to='2026-09-22')


def test_registered_labels_and_toolbar_options_are_validated_and_audited():
    from vera_web_v2_ui_layout import REGISTRY
    label_key = next(k for k,v in REGISTRY.items() if v.get('label') and not v.get('locked'))
    group_key = next(k for k,v in REGISTRY.items() if v.get('group') and not v.get('locked'))
    locked_key = next(k for k,v in REGISTRY.items() if v.get('locked'))
    assert validate_items({label_key:LayoutItem(label='  Tên mới  ')})[label_key]['label']=='Tên mới'
    assert validate_items({group_key:LayoutItem(rows=2,mode='group')})[group_key]['rows']==2
    for item in ({'u-nonexistent':LayoutItem(width=100)}, {locked_key:LayoutItem(width=100)}, {'l-old':LayoutItem(label='New')}):
        with pytest.raises(HTTPException): validate_items(item)
    with pytest.raises(ValidationError): LayoutItem(label='<img src=x onerror=alert(1)>')
    with pytest.raises(ValidationError): LayoutItem(rows=8)
    routes,conn=fixture(install_ui_layout_routes)
    routes['PUT','/v2/ui-layout'](LayoutWrite(device='desktop',revision=2,items={label_key:{'label':'Tên mới'}}),SimpleNamespace(role='admin',employee_username='Admin'))
    audit=[params for sql,params in conn.calls if sql.startswith('INSERT INTO vera_ui_layout_audit')]
    assert len(audit)==1 and audit[0]['actor']=='Admin'
    assert json.loads(audit[0]['before'])['desktop']=={'l-original':{'width':100}}
    assert json.loads(audit[0]['after'])['desktop'][label_key]['label']=='Tên mới'
    before=len(conn.calls)
    for route,args in [(routes['GET','/v2/ui-layout/history'],()),(routes['POST','/v2/ui-layout/restore/{revision}'],(2,LayoutWrite(device='desktop',revision=3,items={})) )]:
        with pytest.raises(HTTPException): route(*args,ident=SimpleNamespace(role='nhanvien'))
    assert len(conn.calls)==before


def test_layout_corrupt_field_falls_back_without_losing_valid_values():
    from vera_web_v2_ui_layout import read_layout
    conn=Conn()
    conn.row['value_json']={'desktop':{'l-valid':{'width':120,'height':999999,'label':'bad'}},'mobile':None}
    # Unregistered labels invalidate that legacy entry; unsupported metadata is never applied.
    assert read_layout(conn)['layout']['desktop']=={}
    conn.row['value_json']['desktop']['l-valid'].pop('label')
    assert read_layout(conn)['layout']['desktop']['l-valid']=={'width':120}
    assert read_layout(conn)['layout']['mobile']=={}


def test_restore_uses_snapshot_and_expected_revision_and_creates_new_audit():
    class HistoryConn(Conn):
        def execute(self,query,params=None):
            self.history_read='SELECT after_json' in str(query)
            return super().execute(query,params)
        def first(self):
            if self.history_read:return {'after_json':{'desktop':{'l-restored':{'width':150}},'mobile':{}}}
            return self.row
    app=App();conn=HistoryConn()
    install_ui_layout_routes(app,engine_instance=lambda:conn,current_identity=lambda:None,identity_type=object)
    result=app.routes['POST','/v2/ui-layout/restore/{revision}'](1,LayoutWrite(device='desktop',revision=2,items={}),SimpleNamespace(role='admin',employee_username='Admin'))
    assert result['revision']==3
    assert result['layout']['desktop']=={'l-restored':{'width':150}}
    assert any(sql.startswith('INSERT INTO vera_ui_layout_audit') for sql,_ in conn.calls)


def test_free_position_offsets_are_preserved_and_bounded():
    item = LayoutItem(offset_x=-180, offset_y=450)
    assert validate_items({'l-free':item})['l-free'] == {'offset_x':-180,'offset_y':450}
    with pytest.raises(ValidationError): LayoutItem(offset_x=2401)
    with pytest.raises(ValidationError): LayoutItem(offset_y=-2401)
