from contextlib import contextmanager
from copy import deepcopy
import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
import pytest

from vera_web_v2_ktv_shifts import change_definition, KtvShiftSave, install_ktv_shift_routes, public_rows
from vera_web_v2_live_tour_roster import shift_label, display_shift_label
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with


def shift(**kwargs):
    return {'ID':'ktv1','Tên ca':'Ca 1','Ca chính':'Ca 1','Giờ bắt đầu':'09:00','Giờ kết thúc':'17:00',
        'Bộ phận':'Nhân viên + Leader','Áp dụng nghỉ giữa ca':True,'Duration nghỉ giữa ca (phút)':90, **kwargs}


def body(**kwargs):
    return {'expected_revision':1, 'name':'Cố định Ca 1','main_shift':'Ca 1','start':'10:00','end':'18:00','fixed':True, **kwargs}


def test_move_ten_to_five_shifts_all_intervening_employees_and_numbers():
    state = state_with(*[employee(f'e{i}',f'NV {i}') for i in range(1,11)])
    live._apply_action(state, 'admin_reorder', {'employee_id':'e10','direction':'position','position':5}, 'letan', NOW)
    records = live._state_response(state, 1, NOW)['records']
    assert [r['_id'] for r in records] == ['e1','e2','e3','e4','e10','e5','e6','e7','e8','e9']
    assert [r['STT'] for r in records] == list(range(1,11))


def test_leave_stays_last_and_has_no_shift_even_when_manually_moved_to_top():
    workers = [employee(f'e{i}',f'NV {i}') for i in range(1,4)]
    workers[1]['work_status'] = 'Nghỉ phép'
    state = state_with(*workers)
    live._apply_action(state,'admin_reorder',{'employee_id':'e2','direction':'top'},'admin',NOW)
    records = live._state_response(state,1,NOW)['records']
    assert records[-1]['_id'] == 'e2'
    assert records[-1]['Vào ca'] == ''
    assert [r['STT'] for r in records] == [1,2,3]


def test_separate_name_main_shift_and_preserve_unrelated_settings():
    definitions = [shift(), shift(**{'ID':'other','Bộ phận':'Locker'})]
    updated, before, after = change_definition(definitions,KtvShiftSave(**body()),'ktv1')
    assert updated[1] == definitions[1]
    assert before == definitions[0]
    assert after['Duration nghỉ giữa ca (phút)'] == 90
    assert after['Tên ca'] == 'Cố định Ca 1'
    assert shift_label(display_shift_label(after),updated) == 'Ca 1'
    updated, _, later = change_definition(updated,KtvShiftSave(**body(name='Buổi tối',main_shift='Ca 2',start='17:00',end='01:00')))
    assert shift_label(display_shift_label(later),updated) == 'Ca 2'
    assert len(public_rows(updated)) == 2


@pytest.mark.parametrize('values', [{'name':' '},{'start':'25:00'},{'end':'10:00'},{'name':'Ca 1'}])
def test_invalid_or_duplicate_shift_is_rejected(values):
    with pytest.raises(HTTPException):
        change_definition([shift()],KtvShiftSave(**body(**values)))


class Database:
    def __init__(self):
        self.definitions = [shift()]
        self.revision = 1
        self.assigned = False
        self.renamed = None
    @contextmanager
    def begin(self):
        before = deepcopy((self.definitions,self.revision,self.renamed))
        try: yield self
        except Exception:
            self.definitions,self.revision,self.renamed=before
            raise
    def execute(self, sql, params=None):
        sql=str(sql);params=params or {};rows=[]
        if 'SELECT value_json' in sql:
            rows=[{'value_json':deepcopy(self.definitions),'revision':self.revision}]
        elif 'INSERT INTO vera_app_setting' in sql:
            self.definitions=json.loads(params['value']);self.revision+=1
        elif 'SELECT username FROM employees' in sql:
            rows=[{'username':'An'}] if self.assigned else []
        elif 'UPDATE employees' in sql:
            assert "('leader','nhanvien')" in sql
            self.renamed=params['new_label']
        else: assert 'pg_advisory_xact_lock' in sql
        class Result:
            def mappings(self):return self
            def first(self):return rows[0] if rows else None
        return Result()


def client_for(db, denied=()):
    class Identity(BaseModel):
        employee_username:str='manager'
    def require(conn,ident,feature):
        if feature in denied:raise HTTPException(403,'Denied')
    app=FastAPI()
    install_ktv_shift_routes(app,engine_instance=lambda:db,current_identity=lambda:Identity(),
        require_feature=require,feature_allowed=lambda conn,ident,feature:feature not in denied)
    return TestClient(app)


def test_routes_create_edit_delete_and_optimistic_revision():
    db=Database();client=client_for(db)
    assert client.get('/v2/staff/ktv-shifts').json()['revision']==1
    saved=client.put('/v2/staff/ktv-shifts/ktv1',json=body())
    assert saved.status_code==200,saved.text
    assert db.renamed=='Cố định Ca 1 (10:00 - 18:00) (Không đổi)'
    assert client.post('/v2/staff/ktv-shifts',json=body(name='Buổi tối')).status_code==409
    created=client.post('/v2/staff/ktv-shifts',json=body(name='Buổi tối',main_shift='Ca 2',expected_revision=2))
    assert created.status_code==200,created.text
    added=created.json()['shifts'][-1]['id']
    db.assigned=True
    assert client.delete(f'/v2/staff/ktv-shifts/{added}?expected_revision=3').status_code==409
    assert db.revision==3
    db.assigned=False
    assert client.delete(f'/v2/staff/ktv-shifts/{added}?expected_revision=3').status_code==200
    assert len(client.get('/v2/staff/ktv-shifts').json()['shifts'])==1
    assert db.definitions[-1]['Trạng thái']=='Đã xóa'


@pytest.mark.parametrize('action,method,url', [('create','post','/v2/staff/ktv-shifts'),('edit','put','/v2/staff/ktv-shifts/ktv1'),('delete','delete','/v2/staff/ktv-shifts/ktv1?expected_revision=1')])
def test_api_enforces_each_mutation_permission(action,method,url):
    db=Database();client=client_for(db,{f'ktv_shift_{action}'})
    response=getattr(client,method)(url,**({'json':body()} if method!='delete' else {}))
    assert response.status_code==403
    assert db.revision==1


def test_view_permission_and_other_department_boundaries():
    db=Database()
    assert client_for(db,{'ktv_shift_view'}).get('/v2/staff/ktv-shifts').status_code==403
    db.definitions=[shift(**{'Bộ phận':'Locker'})]
    assert client_for(db).put('/v2/staff/ktv-shifts/ktv1',json=body()).status_code==404


def test_reorder_positions_ignore_retained_off_roster_assignments():
    workers=[employee(f'e{i}',f'NV {i}') for i in range(1,5)]
    workers[0]['roster_eligible']=False
    state=state_with(*workers)
    live._apply_action(state,'admin_reorder',{'employee_id':'e4','direction':'position','position':2},'admin',NOW)
    assert [r['_id'] for r in live._state_response(state,1,NOW)['records']]==['e2','e4','e3']
    assert len(state['employees'])==4
