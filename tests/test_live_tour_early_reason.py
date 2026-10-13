from copy import deepcopy
from datetime import timedelta
import pytest
from fastapi import HTTPException
import vera_web_v2_live_tour as live
from test_live_tour_backend import NOW, employee, state_with

@pytest.mark.parametrize('remaining,required', [(181,True),(180,False),(179,False),(0,False),(-60,False)])
def test_server_threshold_is_strict_seconds_and_does_not_mutate(remaining, required):
    worker = employee('e1','An')
    worker.update(status='Đang thực hiện', service='Body 90', duration=90, started_at=(NOW-timedelta(seconds=5400-remaining)).isoformat())
    state = state_with(worker); original=deepcopy(state)
    if required:
        with pytest.raises(HTTPException) as error:
            live._require_early_completion_reason(state,'finish_to_pending',{'employee_id':'e1','early_completion_reason':'  '},NOW)
        assert error.value.status_code == 422
        assert error.value.detail['code'] == 'early_completion_reason_required'
    else:
        live._require_early_completion_reason(state,'complete',{'employee_id':'e1'},NOW)
    assert state == original
    live._require_early_completion_reason(state,'complete',{'employee_id':'e1','early_completion_reason':'Khách cần đi sớm'},NOW)


def test_room_reason_survives_pending_paid_and_new_booking_resets():
    from test_live_tour_room_actions import mixed_room
    state=mixed_room()
    with pytest.raises(HTTPException):
        live._require_early_completion_reason(state,'finish_room',{'room':'1'},NOW)
    payload={'room':'1','early_completion_reason':'  Khách có việc gấp  '}
    live._require_early_completion_reason(state,'finish_room',payload,NOW)
    live._apply_action(state,'finish_room',payload,'letan.finish',NOW)
    pending=state['pending'][0]
    assert pending['entries'][0]['early_completion_reason']=='Khách có việc gấp'
    live._apply_action(state,'checkout',{'pending_id':pending['id'],'payment_method':'Tiền mặt','ticket_price':100},'cashier',NOW)
    row=next(row for row in live._service_performance_rows(state) if row.get('early_completion_reason'))
    assert row['early_completion_reason']=='Khách có việc gấp'
    assert row['completed_by']=='letan.finish'
    assert all(not row.get('early_completion_reason') for row in state['employees'])

@pytest.mark.parametrize('reason',[None,42,'a'*1001])
def test_invalid_reason_rejected(reason):
    with pytest.raises(HTTPException):
        live._require_early_completion_reason(state_with(),'complete',{'early_completion_reason':reason},NOW)


def test_http_missing_reason_cannot_commit_and_valid_reason_is_saved(monkeypatch):
    from datetime import datetime
    from test_live_tour_safety import api_client
    worker=employee('e1','An')
    worker.update(status='Đang thực hiện',service='Body 90',duration=90,room='1.1',started_at=datetime.now(live.VN_TZ).isoformat())
    client, shared=api_client(monkeypatch,state_with(worker))
    body={'idempotency_key':'early-reason-http-test','action':'finish_to_pending','expected_revision':1,'payload':{'employee_id':'e1'}}
    response=client.post('/v2/live-tour/action',json=body)
    assert response.status_code==422, response.text
    assert shared['revision']==1 and not shared['state']['pending']
    assert response.json()['detail']['code']=='early_completion_reason_required'
    body['payload']['early_completion_reason']='Khách có lịch hẹn'
    response=client.post('/v2/live-tour/action',json=body)
    assert response.status_code==200, response.text
    assert shared['state']['pending'][0]['entries'][0]['early_completion_reason']=='Khách có lịch hẹn'
