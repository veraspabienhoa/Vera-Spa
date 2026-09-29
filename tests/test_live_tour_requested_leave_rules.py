from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from vera_leave_registration_shared import validate_registration_rule, LeaveRuleError
import vera_missing_checkin_notifications as alerts

@pytest.mark.parametrize('role', ['admin','quanly','letan','nhanvien'])
@pytest.mark.parametrize('reason', ['Về sớm CUỐI TUẦN CÓ phép','Đi trễ CUỐI TUẦN KHÔNG phép','Nghỉ CUỐI TUẦN CÓ phép'])
def test_weekend_label_never_accepts_tuesday_even_when_catalog_is_blank(role, reason):
    with pytest.raises(LeaveRuleError):
        validate_registration_rule({'name':reason},role,date(2026,9,29))
    validate_registration_rule({'name':reason},'admin',date(2026,10,3))
    validate_registration_rule({'name':reason},'admin',date(2026,10,4))

@pytest.mark.parametrize('shift,hour', [('Ca 1',15),('Ca 2',17)])
@pytest.mark.parametrize('reason', ['Đi trễ CÓ phép','Đi trễ KHÔNG phép','Đi trễ CUỐI TUẦN CÓ phép','Đi trễ CUỐI TUẦN KHÔNG phép','Đi trễ phát sinh'])
def test_registered_late_alert_at_standard_cutoff(monkeypatch,shift,hour,reason):
    zone=timezone(timedelta(hours=7));now=datetime(2026,9,29,hour,0,tzinfo=zone)
    checked=[]
    class Result:
        def __init__(self,rows):self.rows=rows
        def mappings(self):return self
        def all(self):return self.rows
    class Conn:
        def execute(self,query,params):
            if 'vera_dataset_cache' in str(query):
                return Result([{'payload':[{'EmployeeName':'Other'},*checked], 'updated_at':now-timedelta(minutes=1)}])
            return Result([{'employee_name':'Test','leave_reason':reason}])
    monkeypatch.setattr(alerts,'_staff_scheduled_rows',lambda *a:[{'employee_username':'Test','employee_name':'Test','employee_role':'nhanvien','shift_code':shift,'start_time':'10:00'}])
    monkeypatch.setattr(alerts,'_scheduled_rows',lambda *a:[])
    import vera_attendance_source
    monkeypatch.setattr(vera_attendance_source,'source_for',lambda *a:'timesoft')
    ident=SimpleNamespace(role='admin',employee_username='Admin')
    assert alerts.current_missing_checkins(Conn(),ident,now-timedelta(seconds=1))==[]
    result=alerts.current_missing_checkins(Conn(),ident,now)
    assert len(result)==1 and 'đã đăng ký đi trễ' in result[0]['body']
    checked.append({'EmployeeName':'Test','MachineTimeCheckInStr':f'29/09/2026 {hour-1}:00:00'})
    assert alerts.current_missing_checkins(Conn(),ident,now)==[]
