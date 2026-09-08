"""Synthetic, read-only browser fixture using the real Live Tour response schema."""
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import vera_web_v2_live_tour as live  # noqa: E402


def preview_response(admin=True):
    now = datetime.now(live.VN_TZ)
    state = live._empty_state(now)
    state["rooms"].extend({"id": f"preview-18-{bed}", "name": f"18.{bed}", "active": True} for bed in (3, 4))
    for index in range(1, 13):
        state["employees"].append({
            "id": f"demo-{index}", "stt": index, "sort_index": index,
            "name": f"Nhân viên mẫu {index:02d}", "shift": "Ca 1" if index < 7 else "Ca 2",
            "work_status": "Nghỉ" if index == 12 else "Đi làm",
            "hidden": False, "vip": index < 5,
        })
    live._booking(state, {"employee_id": "demo-1", "room": "19.1", "service": "VIP 90 PR"}, now)
    for index in range(2, 6):
        live._booking(state, {"employee_id": f"demo-{index}", "room": f"18.{index - 1}", "service": "Body 90"}, now)
    live._apply_action(state, "start_break", {"employee_id": "demo-6"}, "Tài khoản mẫu", now - timedelta(minutes=95))
    live._apply_action(state, "end_break", {"employee_id": "demo-6"}, "Tài khoản mẫu", now)
    return live._state_response(state, 1, now, can_admin=admin, can_operate=admin,
                                can_payment=admin, can_export=admin)


if __name__ == "__main__":
    print(json.dumps({"admin": preview_response(), "viewer": preview_response(False)}, ensure_ascii=False))
