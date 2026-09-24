from contextlib import contextmanager
from types import SimpleNamespace
import pytest
from fastapi import FastAPI, HTTPException
import vera_web_v2_notification_settings as settings
import vera_web_v2_live_tour as live
from test_notification_routing import Identity

@pytest.mark.parametrize('role', ['quanly', 'letan', 'nhanvien', 'leader'])
def test_recovery_status_and_retry_admin_only(role):
    app=FastAPI()
    def forbidden(): raise AssertionError('database touched before authorization')
    live.install_live_tour_routes(app,engine_instance=forbidden,current_identity=lambda:None,
        require_feature=lambda *a:None,feature_allowed=lambda *a:True,identity_type=Identity)
    for path in ['/v2/live-tour/recovery','/v2/live-tour/recovery/retry']:
        endpoint=next(r.endpoint for r in app.routes if r.path==path)
        with pytest.raises(HTTPException) as exc: endpoint(ident=Identity(role=role))
        assert exc.value.status_code==403

@pytest.mark.parametrize('available', [True,False])
def test_detail_scoped_to_recipient_and_current_routing(monkeypatch,available):
    monkeypatch.setattr(settings,'ensure_schema',lambda c:None)
    # imported inside installer from delivery
    import vera_notification_delivery as delivery
    monkeypatch.setattr(settings,'ensure_routing_schema',lambda c:None)
    queries=[]
    class Connection:
        def execute(self,statement,params):
            queries.append((str(statement),params))
            return SimpleNamespace(mappings=lambda:SimpleNamespace(first=lambda: {'id':42,'payload':{'body':'private'}} if available else None))
    class Engine:
        @contextmanager
        def begin(self): yield Connection()
    app=FastAPI()
    settings.install_notification_settings_routes(app,engine_instance=Engine,current_identity=lambda:None,identity_type=Identity)
    endpoint=next(r.endpoint for r in app.routes if r.path=='/v2/notification-inbox/{notification_id}')
    if available: assert endpoint(42,Identity())['id']==42
    else:
        with pytest.raises(HTTPException) as exc: endpoint(42,Identity())
        assert exc.value.status_code==404
    sql,params=queries[-1]
    assert 'd.id=:id AND d.recipient=:recipient' in sql
    assert params=={'id':42,'recipient':Identity().auth_user_id}
    assert 'p.is_active' in sql and 'r.channels ? d.channel' in sql and 'COALESCE(s.enabled,TRUE)' in sql
