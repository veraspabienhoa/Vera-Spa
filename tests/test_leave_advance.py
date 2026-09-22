from datetime import date
import pandas as pd
from vera_leave_advance import balances, is_approved_sick
from vera_leave_registration_live_shared import validate_leave_registration_request_live
from test_annual_leave_quota_isolation import _runtime, _credentials, _request

SICK='Nghỉ bệnh có giấy khám hoặc được quản lý duyệt'
def r(day, days=1, reason='Nghỉ CÓ phép'):
    return {'Ngày':day,'Tên nhân viên':'Minh Anh','Lý do nghỉ':reason,'Số ngày tính':days}


def test_borrow_exact_days_rebuild_after_edit_delete_and_year_boundary():
    normal=[r(date(2026,12,d)) for d in range(1,6)]
    sick=r(date(2026,12,8),1.5,SICK)
    result=balances(normal+[sick],date(2027,1,1))
    assert result['2026-12']['borrowed']==1.5
    assert result['2027-01']['remaining']==3.5
    assert balances(normal+[dict(sick,**{'Số ngày tính':.5})],date(2027,1,1))['2027-01']['remaining']==4.5
    assert balances(normal,date(2027,1,1))['2027-01']['remaining']==5


def test_only_overflow_and_all_three_exact_reasons_and_zero_days():
    for prefix in ['Nghỉ','Về sớm','Đi trễ']:
        reason=f'{prefix} bệnh có giấy khám hoặc được quản lý duyệt'
        assert is_approved_sick(reason)
        assert balances([r(date(2026,9,1),4),r(date(2026,9,2),.5,reason)],date(2026,10,1))['2026-10']['remaining']==5
        assert balances([r(date(2026,9,1),5),r(date(2026,9,2),.5,reason)],date(2026,10,1))['2026-10']['remaining']==4.5
        assert balances([r(date(2026,9,1),5),r(date(2026,9,2),0,reason)],date(2026,10,1))['2026-10']['remaining']==5
    for reason in ['Nghỉ Phép năm','Nghỉ phép quay video','Nghỉ KHÔNG phép','Nghỉ PHÁT SINH']:
        assert balances([r(date(2026,9,1),5),r(date(2026,9,2),2,reason)],date(2026,10,1))['2026-10']['remaining']==5


def test_debt_never_negative_and_idle_month_repays_remaining_debt():
    result=balances([r(date(2026,9,1),5),r(date(2026,9,2),7,SICK)],date(2026,12,1))
    assert result['2026-10']['available']==0
    assert result['2026-11']['available']==3
    assert result['2026-12']['available']==5


def test_canonical_create_edit_preview_enforces_reduced_allowance_and_admin_override():
    rows=[r(date(2026,9,d)) for d in range(1,6)]+[r(date(2026,9,8),2,SICK)]
    rows += [r(date(2026,10,d)) for d in range(1,4)]
    history=pd.DataFrame(rows)
    request=_request(when=date(2026,10,14))
    result=validate_leave_registration_request_live(request,history,_credentials(),_runtime())
    assert not result['ok']
    assert 'đã ứng từ tháng trước 2' in result['errors'][0]
    request['role']='admin'
    assert validate_leave_registration_request_live(request,history,_credentials(),_runtime())['ok']
    request['role']='nhanvien'; request['reason']=SICK
    result=validate_leave_registration_request_live(request,history,_credentials(),_runtime())
    assert result['ok']
    assert any('tháng kế tiếp bị trừ 1' in warning for warning in result['warnings'])


def test_alert_does_not_mark_approved_borrow_as_violation_but_detects_next_month_excess():
    from vera_leave_quota_alerts import summarize
    rows=[dict(leave_date=date(2026,9,1),employee_name='Minh Anh',leave_reason='Nghỉ CÓ phép',leave_type='Có phép',calculated_days=5),dict(leave_date=date(2026,9,8),employee_name='Minh Anh',leave_reason=SICK,leave_type='Được duyệt',calculated_days=2)]
    assert summarize(rows)==[]
    rows.append(dict(rows[0],leave_date=date(2026,10,1),calculated_days=4))
    result=summarize(rows)
    assert len(result)==1 and result[0]['month']=='2026-10'
    assert result[0]['day_limit']==3


def test_empty_months_in_multimonth_request_have_allowance():
    result=balances([],date(2026,10,31),since=date(2026,9,1))
    assert result['2026-09']['remaining']==result['2026-10']['remaining']==5


def test_canonical_partial_sick_reasons_can_borrow():
    history=pd.DataFrame([r(date(2026,10,d)) for d in range(1,6)])
    for prefix in ['Về sớm','Đi trễ']:
        req=_request(reason=f'{prefix} bệnh có giấy khám hoặc được quản lý duyệt')
        req['days']=.5
        result=validate_leave_registration_request_live(req,history,_credentials(),_runtime())
        assert result['ok'], result['errors']
        assert any('tháng kế tiếp bị trừ 0.5' in warning for warning in result['warnings'])
