from datetime import date, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import text

import vera_holiday_leave as holiday
import vera_web_v2_permissions as permissions
import vera_web_v2_live_tour as live
from test_live_tour_resource_postgres import database
from test_live_tour_backend import employee, state_with

DAY = date(2026, 10, 20)
def at(clock, day=DAY): return datetime.fromisoformat(f'{day}T{clock}:00+07:00')
def body(**updates):
    return holiday.HolidayCreate(request_id=uuid4(), scope='all', mode='day', dates=[DAY], note='Nghỉ lễ', **updates)


def test_single_and_non_contiguous_days_have_inclusive_dates_exclusive_end():
    assert holiday.periods_for(body()) == [(at('00:00'), at('00:00', DAY+timedelta(days=1)))]
    value = body().model_copy(update={'mode':'dates','dates':[DAY+timedelta(days=2),DAY,DAY]})
    assert holiday.periods_for(value) == [(at('00:00'),at('00:00',DAY+timedelta(days=1))), (at('00:00',DAY+timedelta(days=2)),at('00:00',DAY+timedelta(days=3)))]


def test_day_range_and_hours_through_midnight_use_vietnam_time():
    value = body().model_copy(update={'mode':'range','dates':[],'date_from':DAY,'date_to':DAY+timedelta(days=2)})
    assert holiday.periods_for(value) == [(at('00:00'),at('00:00',DAY+timedelta(days=3)))]
    value = body().model_copy(update={'mode':'hours','dates':[],'starts_at':datetime(2026,10,20,23),'ends_at':datetime(2026,10,21,2)})
    assert holiday.periods_for(value) == [(at('23:00'),at('02:00',DAY+timedelta(days=1)))]


@pytest.mark.parametrize('changes', [{'dates':[]}, {'note':' '}, {'mode':'day','dates':[DAY,DAY+timedelta(days=1)]},
    {'mode':'range','dates':[],'date_from':DAY,'date_to':DAY-timedelta(days=1)},
    {'mode':'hours','dates':[],'starts_at':at('12:00'),'ends_at':at('10:00')},
    {'mode':'day','starts_at':at('10:00')}])
def test_invalid_or_mixed_periods_rejected(changes):
    with pytest.raises(HTTPException): holiday.periods_for(body().model_copy(update=changes))


def test_hr_scope_does_not_follow_account_role():
    people = [{'username':'An','department':'locker','role':'letan'}, {'username':'Bình','department':'letan','role':'locker'}]
    value = body().model_copy(update={'scope':'departments','departments':['locker']})
    assert holiday.select_members(value,people,[{'code':'locker'},{'code':'letan'}]) == [people[0]]
    with pytest.raises(HTTPException): holiday.select_members(value,people,[{'code':'letan'}])


def test_interval_union_partial_hours_and_midnight_boundaries():
    periods=[{'starts_at':at('10:00'),'ends_at':at('12:00')},{'starts_at':at('11:00'),'ends_at':at('13:00')}]
    assert holiday.uncovered(at('09:00'),at('17:00'),periods) == [(at('09:00'),at('10:00')),(at('13:00'),at('17:00'))]
    worker = employee('e1','An')
    worker.update(service='Existing service',started_at=at('09:00').isoformat(),status='Đang thực hiện')
    state=state_with(worker)
    periods[0].update(note='Lễ')
    holiday.project_live(state,{'An':[periods[0]]},at('10:00'))
    assert state['employees'][0]['holiday_leave_active']
    assert state['employees'][0]['service'] == 'Existing service'
    holiday.project_live(state,{'An':[periods[0]]},at('12:00'))
    assert not state['employees'][0]['holiday_leave_active']


def test_holiday_blocks_admin_booking_and_start_but_keeps_service():
    worker=employee('e1','An'); worker['holiday_leave_active']=True
    state=state_with(worker)
    with pytest.raises(HTTPException): live._booking(state,{'employee_id':'e1'},at('10:00'),outside_shift=True)
    with pytest.raises(HTTPException): live._start_employee(state,worker,at('10:00'),admin_start=True)


def test_attendance_subtracts_only_approved_lateness_keeps_scan_and_pay_evidence():
    row={'date':'20/10/2026','employee_name':'An','shift_start':'09:00','shift_end':'17:00','check_in_at':at('11:00').isoformat(),'check_in':'11:00','attendance_expected':True,'payable_minutes_verified':True}
    periods=[{'starts_at':at('09:00'),'ends_at':at('10:00'),'note':'Lễ'}]
    holiday.apply_attendance([row],{'An':periods})
    assert row['late_minutes']==60 and row['attendance_expected']
    assert row['check_in']=='11:00' and row['payable_minutes_verified']
    holiday.apply_attendance([row],{'An':[{'starts_at':at('00:00'),'ends_at':at('00:00',DAY+timedelta(days=1)),'note':'Lễ'}]})
    assert row['holiday_leave_full_shift'] and not row['attendance_expected']
    assert row['late_minutes']==0


def test_hc_wage_penalty_excludes_only_holiday_hours():
    import vera_hc_rules as hc
    config=dict(calculation_mode='hourly',rate_ca1=30000,rate_ca2_before_22=40000,rate_ca2_after_22=60000)
    row=dict(main_start='09:00',main_end='17:00',shift_code='Ca 1',overtime_shift='')
    decision={'kind':'absence','start':at('09:00'),'end':at('17:00'), 'holiday_periods':[{'starts_at':at('10:00').isoformat(),'ends_at':at('12:00').isoformat()}]}
    assert hc.decision_penalty(config,row,DAY,decision)==360000
    assert len(decision['wage_segments'])==2


def test_new_permissions_are_on_birthday_page_and_default_ungranted():
    assert permissions.FEATURE_DEPENDENCIES['holiday_leave_register']=={'birthday'}
    assert 'holiday_leave_cancel' in permissions.FEATURES
    for role, defaults in permissions.DEFAULT_ROLE_FEATURES.items():
        if role == 'admin': continue
        assert 'holiday_leave_register' not in defaults and 'holiday_leave_cancel' not in defaults


def prepare(database):
    with database.begin() as conn:
        conn.execute(text('''ALTER TABLE employees ADD PRIMARY KEY(username), ADD COLUMN role text,
            ADD COLUMN payload jsonb DEFAULT '{}'::jsonb, ADD COLUMN stt integer;
            INSERT INTO employees(username,full_name,role,stt) VALUES('An','An Test','letan',1),('Bình','Binh Test','locker',2),('Admin','Admin','admin',3);
            INSERT INTO vera_app_setting VALUES('payroll','hr_registry','{"assignments":{"An":"locker","Bình":"letan"}}',1,NOW());'''))
    allowed={'birthday','holiday_leave_register','holiday_leave_cancel'}
    identity=SimpleNamespace(employee_username='Admin',role='admin')
    def require(conn, ident, feature):
        if feature not in allowed: raise HTTPException(403,'denied')
    app=FastAPI()
    holiday.install_routes(app,engine_instance=lambda:database,current_identity=lambda:identity,require_feature=require,
        feature_allowed=lambda conn,ident,feature:feature in allowed,identity_type=SimpleNamespace)
    return TestClient(app),allowed,identity


def send(api, **changes):
    value=body().model_dump(mode='json');value.update(changes)
    return api.post('/v2/holiday-leave',json=value),value


def test_postgres_cohort_idempotence_overlap_and_cancellation(database):
    api,allowed,identity=prepare(database)
    with database.begin() as conn:
        conn.execute(text('CREATE TABLE leave_records(calculated_days numeric); INSERT INTO leave_records VALUES(1),(0.5)'))
    result,payload=send(api,scope='departments',departments=['locker'])
    assert result.status_code==200,result.text
    assert result.json()['employee_count']==1
    assert result.json()['calculated_days']==0
    listed=api.get('/v2/holiday-leave?start=2026-10-01&end=2026-10-31').json()
    assert listed['registrations'][0]['calculated_days']==0
    assert api.post('/v2/holiday-leave',json=payload).json()['duplicate']
    assert api.post('/v2/holiday-leave',json={**payload,'note':'Different'}).status_code==409
    with database.begin() as conn:
        assert conn.execute(text('SELECT employee_username FROM vera_holiday_leave_member')).scalar()=='An'
        # Changing department later does not alter the registered membership.
        conn.execute(text("UPDATE vera_app_setting SET value_json='{}' WHERE category='payroll'"))
        assert holiday.intervals(conn,at('10:00'),at('11:00')).keys()=={'An'}
    assert send(api,scope='employees',employees=['An'])[0].status_code==409
    ident=result.json()['id']
    assert api.post(f'/v2/holiday-leave/{ident}/cancel',json={'revision':2}).status_code==409
    assert api.post(f'/v2/holiday-leave/{ident}/cancel',json={'revision':1}).status_code==200
    with database.begin() as conn:
        assert holiday.intervals(conn,at('10:00'),at('11:00'))=={}
    assert send(api,scope='employees',employees=['An'])[0].status_code==200
    with database.begin() as conn:
        assert float(conn.execute(text('SELECT sum(calculated_days) FROM leave_records')).scalar())==1.5
        assert conn.execute(text('SELECT count(*) FROM leave_records')).scalar()==2


def test_postgres_permissions_personal_privacy_and_no_inherited_holiday(database):
    api,allowed,identity=prepare(database)
    assert send(api)[0].status_code==200
    allowed.remove('holiday_leave_register');allowed.remove('holiday_leave_cancel')
    identity.employee_username='An';identity.role='letan'
    result=api.get('/v2/holiday-leave?start=2026-10-01&end=2026-10-31').json()
    assert not result['can_register'] and result['employees']==[]
    assert result['registrations'][0]['employees']==[{'username':'An','department':'locker'}]
    assert send(api)[0].status_code==403
    with database.begin() as conn:
        conn.execute(text("UPDATE employees SET username='Assistant' WHERE username='An'"))
        assert 'Assistant' in holiday.intervals(conn,at('10:00'),at('11:00'))
        conn.execute(text("DELETE FROM employees WHERE username='Assistant'"))
        conn.execute(text("INSERT INTO employees(username,role) VALUES('Assistant','letan')"))
        assert 'Assistant' not in holiday.intervals(conn,at('10:00'),at('11:00'))


def test_postgres_invalid_cohort_and_entire_overlap_rollback(database):
    api,allowed,identity=prepare(database)
    assert send(api,scope='employees',employees=['Unknown'])[0].status_code==422
    result,_=send(api,scope='employees',employees=['An'])
    assert result.status_code==200
    result,_=send(api)
    assert result.status_code==409
    with database.begin() as conn:
        assert conn.execute(text('SELECT count(*) FROM vera_holiday_leave')).scalar()==1
        assert conn.execute(text('SELECT count(*) FROM vera_holiday_leave_member')).scalar()==1


def test_postgres_future_booking_guard_is_fresh_and_limited_to_action_targets(database):
    api,allowed,identity=prepare(database)
    assert send(api,scope='employees',employees=['An'])[0].status_code==200
    state=state_with(employee('e1','An'),employee('e2','Bình'))
    with database.begin() as conn:
        holiday.refresh_action_holidays(conn,state,'booking',{'employee_id':'e2','booked_at':at('10:00').isoformat()},at('09:00',DAY-timedelta(days=1)))
        assert not state['employees'][1].get('holiday_leave_active')
        with pytest.raises(HTTPException):
            holiday.refresh_action_holidays(conn,state,'booking',{'employee_id':'e1','booked_at':at('10:00').isoformat()},at('09:00',DAY-timedelta(days=1)))
