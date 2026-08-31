"""Authenticated Web V2 control/status API for PostgreSQL Auto Check."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel

import vera_auto_check as core


class AutoCheckConfig(BaseModel):
    status: str | None = None
    threshold_minutes: int | None = None


def install_auto_check_routes(app, *, engine_instance: Callable[[], Any], current_identity, require_feature, identity_type):
    @app.get("/v2/auto-check")
    def auto_check_dashboard(limit: int = 100, identity: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, identity, "auto_penalty")
            return core.dashboard(conn, limit)

    @app.put("/v2/auto-check/config")
    def update_auto_check_config(body: AutoCheckConfig, identity: identity_type = Depends(current_identity)):
        updates = body.model_dump(exclude_none=True) if hasattr(body, "model_dump") else body.dict(exclude_none=True)
        if "status" in updates and str(updates["status"]).upper() not in {"RUNNING", "PAUSED"}:
            raise HTTPException(status_code=422, detail="Trạng thái chỉ nhận RUNNING hoặc PAUSED.")
        with engine_instance().begin() as conn:
            require_feature(conn, identity, "auto_penalty_control")
            return {"ok": True, "config": core.save_config(conn, updates, identity.employee_username)}

    @app.post("/v2/auto-check/run")
    def request_auto_check_run(identity: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            require_feature(conn, identity, "auto_penalty_run")
            cfg = core.load_config(conn)
            if cfg.get("status") == "PAUSED":
                raise HTTPException(status_code=409, detail="Auto Check đang tạm dừng. Hãy mở lại trước khi chạy.")
            cfg = core.save_config(conn, {"manual_run_requested": True}, identity.employee_username)
        return {"ok": True, "queued": True, "message": "Đã xếp hàng. Job gần nhất sẽ chạy Auto Check.", "config": cfg}
