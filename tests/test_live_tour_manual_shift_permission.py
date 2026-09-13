import pytest
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import vera_web_v2_live_tour as live


class Identity(BaseModel):
    role: str
    employee_username: str = "test"


@pytest.mark.parametrize("role", ["quanly", "letan", "locker", "nhanvien"])
def test_manual_shift_rejects_non_admin_before_accessing_database(role):
    def forbidden():
        raise AssertionError("Unauthorized shift must not access database")

    app = FastAPI()
    live.install_live_tour_routes(
        app, engine_instance=forbidden, current_identity=lambda: Identity(role=role),
        require_feature=lambda *args: None, feature_allowed=lambda *args: True,
        identity_type=Identity,
    )
    endpoint = next(route.endpoint for route in app.routes if getattr(route, "path", "") == "/v2/live-tour/action")
    with pytest.raises(HTTPException) as error:
        endpoint(live.LiveTourAction(action="set_shift", payload={"employee_id": "e1", "shift": "Ca 1"}), Identity(role=role))
    assert error.value.status_code == 403
