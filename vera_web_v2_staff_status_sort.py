"""Status-first ordering for the Web V2 employee list."""
from __future__ import annotations

from fastapi import Depends


STATUS_RANK = {
    "Đang làm việc": 0,
    "Tạm thời nghỉ việc": 1,
    "Đã nghỉ việc": 2,
}
ROLE_RANK = {
    "leader": 0,
    "nhanvien": 1,
    "quanly": 2,
    "letan": 3,
    "locker": 4,
    "tapvu": 5,
    "admin": 6,
}


def _remove_route(app, path: str, method: str):
    method = method.upper()
    for route in list(app.router.routes):
        if getattr(route, "path", None) == path and method in (getattr(route, "methods", set()) or set()):
            app.router.routes.remove(route)
            return getattr(route, "endpoint", None)
    return None


def install_staff_status_sort(app, *, current_identity, identity_type) -> None:
    if getattr(app.state, "staff_status_sort_installed", False):
        return
    original_staff = _remove_route(app, "/v2/staff", "GET")
    if not callable(original_staff):
        raise RuntimeError("Không tìm thấy route /v2/staff để cài sắp xếp trạng thái.")

    @app.get("/v2/staff")
    def staff_status_first(ident: identity_type = Depends(current_identity)):
        payload = original_staff(ident=ident)
        output = dict(payload or {})
        employees = [dict(item) for item in (output.get("employees") or [])]
        employees.sort(key=lambda item: (
            STATUS_RANK.get(str(item.get("employment_status") or ""), 99),
            ROLE_RANK.get(str(item.get("role") or "").lower(), 99),
            str(item.get("full_name") or item.get("username") or "").casefold(),
            str(item.get("username") or "").casefold(),
        ))
        output["employees"] = employees
        output["sort_order"] = ["Đang làm việc", "Tạm thời nghỉ việc", "Đã nghỉ việc"]
        return output

    app.state.staff_status_sort_installed = True
