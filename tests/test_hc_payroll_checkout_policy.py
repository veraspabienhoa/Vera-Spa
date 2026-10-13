from copy import deepcopy
from datetime import date, datetime
import pytest
import vera_web_v2_department_payroll as dep

DAY=date(2026,10,13)
norm=lambda value:str(value or '').strip().casefold()

def totals(department,shift,arrival,departure='',**extra):
    definitions={department:{'Ca 1':{'start':'09:00','end':'17:00'},'Ca 2':{'start':'16:30','end':'00:30'}}}
    schedule={'employee_username':'staff','work_date':DAY,'schedule_department':department,'shift_code':shift,**extra.pop('schedule_extra',{})}
    row={'employee_name':'staff','date':'13/10/2026','check_in':arrival,'check_out':departure,**extra}
    original=deepcopy(row)
    result=dep._attendance_totals([row],'staff',norm,dep.DEFAULT_CONFIG['letan'],schedule_records=[schedule],definitions=definitions,department=department)
    assert row==original
    return result

@pytest.mark.parametrize('department',['letan','locker','quanly','tapvu','support','custom_hc'])
def test_missing_checkout_uses_department_shift_end_without_paying_early_arrival(department):
    result=totals(department,'Ca 2','16:29:11',attendance_pending=True)
    assert result['pending_dates']==[]
    assert result['minutes_ca2_before_22']==330
    assert result['minutes_ca2_after_22']==150


def test_yen_linh_checkout_after_shift_is_capped_and_seconds_preserved():
    result=totals('letan','Ca 1','09:06:43','17:04:52')
    assert result['minutes_ca1']==pytest.approx(473+17/60)


def test_overtime_extends_pay_only_when_registered_and_early_exit_still_counts():
    result=totals('letan','Ca 1','09:00','18:00',schedule_extra={'overtime_shift':'Từ giờ tới giờ','overtime_start_time':'17:00','overtime_end_time':'18:00'})
    assert result['minutes_ca1']+result['minutes_ca2_before_22']==540
    assert totals('letan','Ca 1','09:00','16:00')['minutes_ca1']==420


def test_missing_arrival_and_unresolved_evidence_are_not_paid():
    assert totals('letan','Ca 1','')['pending_dates']==[DAY.isoformat()]
    result=totals('letan','Ca 1','09:00',attendance_pending=True,attendance_evidence_issues=['conflict'])
    assert result['pending_dates']==[DAY.isoformat()]
    assert result['minutes_ca1']==0


def test_unmapped_pending_reason_cannot_be_overridden_by_checkout_default():
    result=totals('letan','Ca 1','09:00',attendance_pending=True,attendance_pending_reasons=['missing_check_out','unmapped_employee'])
    assert result['pending_dates']==[DAY.isoformat()]
    assert result['minutes_ca1']==0
