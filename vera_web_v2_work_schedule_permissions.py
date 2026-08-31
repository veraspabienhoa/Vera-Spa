"""Granular permissions and directory-list visibility for VERA Web V2.

Adds exactly three schedule permissions to the existing Phân quyền system:
- work_schedule_quanly: lịch Quản lý
- work_schedule_letan: lịch Lễ tân
- work_schedule_locker: lịch Locker

Also registers the ``giamdoc`` (Giám đốc) role across Web V2 employee management,
permission defaults, employee ordering, department labels, and Nội quy role-token
parsing. Giám đốc starts from the same base feature set as Quản lý/Lễ tân, while
sensitive actions that are explicitly Admin-only remain Admin-only.

Thanh Dung and Thu Trang are management accounts that must remain valid accounts
and keep historical data, but they are intentionally hidden from employee/account
directory lists throughout Web V2. Historical records are not removed because the
filter only applies to named directory collections such as ``employees`` and
``accounts`` in JSON responses.
"""
from __future__ import annotations

import json
import re
import unicodedata
from typing import Any

from starlette.responses import Response

import vera_leave_registration_shared as leave_rules
import vera_web_v2_permissions as permissions
import vera_web_v2_staff as staff
import vera_web_v2_staff_status_sort as staff_sort


WORK_SCHEDULE_PERMISSION_GROUP = {
    "work_schedule_quanly": "Lịch làm việc · Quản lý",
    "work_schedule_letan": "Lịch làm việc · Lễ tân",
    "work_schedule_locker": "Lịch làm việc · Locker",
}

GIAMDOC_ROLE = "giamdoc"
GIAMDOC_LABEL = "Giám đốc"

# Exact directory identities requested by operations. Keep both spaced and compact
# forms because old employee rows may use either style for username/full_name.
HIDDEN_DIRECTORY_IDENTITIES = {
    "thanh dung",
    "thanhdung",
    "thu trang",
    "thutrang",
}

# Only these account-directory collections are filtered. Transaction/history keys
# such as records, rows, changes, payroll history, leave history, etc. stay intact.
DIRECTORY_LIST_KEYS = {
    "employees",
    "accounts",
    "staff",
    "users",
    "people",
    "employee_options",
    "employee_list",
    "employee_catalog",
    "employee_choices",
    "eligible_employees",
    "employee_targets",
    "recipients",
    "assignees",
}

IDENTITY_KEYS = (
    "username",
    "full_name",
    "employee_username",
    "employee_name",
    "name",
    "label",
    "value",
    "target",
    "Tên nhân viên",
    "Họ và tên",
    "Họ và tên đầy đủ",
)


def _norm_identity(value: Any) -> str:
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Mn")
    text = text.replace("đ", "d")
    return re.sub(r"\s+", " ", text).strip()


def _is_hidden_directory_account(item: Any) -> bool:
    if not isinstance(item, dict):
        return False
    for key in IDENTITY_KEYS:
        value = _norm_identity(item.get(key))
        if not value:
            continue
        if value in HIDDEN_DIRECTORY_IDENTITIES or value.replace(" ", "") in HIDDEN_DIRECTORY_IDENTITIES:
            return True
    return False


def _sanitize_directory_payload(value: Any, parent_key: str = "") -> Any:
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, child in value.items():
            key_text = str(key or "")
            if isinstance(child, list) and key_text in DIRECTORY_LIST_KEYS:
                output[key] = [
                    _sanitize_directory_payload(item, key_text)
                    for item in child
                    if not _is_hidden_directory_account(item)
                ]
            else:
                output[key] = _sanitize_directory_payload(child, key_text)
        return output
    if isinstance(value, list):
        return [_sanitize_directory_payload(item, parent_key) for item in value]
    return value


def _install_directory_visibility_middleware() -> None:
    # Import lazily to avoid an import cycle while vera_web_v2_api_v38 is loading.
    import vera_web_v2_api_shared as shared

    app = shared.app
    if getattr(app.state, "hidden_directory_accounts_middleware_installed", False):
        return

    @app.middleware("http")
    async def hide_directory_accounts(request, call_next):
        response = await call_next(request)
        content_type = str(response.headers.get("content-type") or "").lower()
        if "application/json" not in content_type:
            return response

        chunks: list[bytes] = []
        async for chunk in response.body_iterator:
            if isinstance(chunk, bytes):
                chunks.append(chunk)
            else:
                chunks.append(str(chunk).encode("utf-8"))
        raw = b"".join(chunks)

        try:
            payload = json.loads(raw.decode("utf-8"))
            filtered = _sanitize_directory_payload(payload)
            body = json.dumps(filtered, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        except Exception:
            body = raw

        headers = dict(response.headers)
        headers.pop("content-length", None)
        return Response(
            content=body,
            status_code=response.status_code,
            headers=headers,
            media_type=None,
            background=response.background,
        )

    app.state.hidden_directory_accounts_middleware_installed = True


def _add_role_token(parser, normalizer):
    """Wrap a role-token parser so both giamdoc and Giám đốc map to giamdoc."""
    if getattr(parser, "_vera_giamdoc_enabled", False):
        return parser

    def wrapped(value: str) -> set[str]:
        result = set(parser(value))
        normalized = str(normalizer(value) or "")
        compact = normalized.replace(" ", "")
        if "giamdoc" in compact or "giam doc" in normalized:
            result.add(GIAMDOC_ROLE)
        return result

    wrapped._vera_giamdoc_enabled = True
    return wrapped


def _install_giamdoc_role() -> None:
    """Register Giám đốc without changing existing Admin-only safeguards."""
    if GIAMDOC_ROLE not in permissions.ROLES:
        permissions.ROLES.insert(0, GIAMDOC_ROLE)

    # Use the established management baseline. Work-schedule permissions remain
    # separately assignable because that module deliberately has only 3 groups:
    # Quản lý, Lễ tân and Locker.
    permissions.DEFAULT_ROLE_FEATURES.setdefault(GIAMDOC_ROLE, set(permissions.FRONTDESK))

    if GIAMDOC_ROLE not in staff.ALL_ROLES:
        try:
            index = staff.ALL_ROLES.index("quanly")
        except ValueError:
            index = len(staff.ALL_ROLES)
        staff.ALL_ROLES.insert(index, GIAMDOC_ROLE)

    if GIAMDOC_ROLE not in staff.ROLE_ORDER:
        staff.ROLE_ORDER.insert(0, GIAMDOC_ROLE)

    if GIAMDOC_LABEL not in staff.DEPARTMENT_ORDER:
        try:
            index = staff.DEPARTMENT_ORDER.index("Quản lý")
        except ValueError:
            index = 0
        staff.DEPARTMENT_ORDER.insert(index, GIAMDOC_LABEL)

    # Keep the old staff department function for every existing role.
    if not getattr(staff, "_giamdoc_department_installed", False):
        original_department = staff._department

        def department_with_giamdoc(role: str) -> str:
            if str(role or "").strip().lower() == GIAMDOC_ROLE:
                return GIAMDOC_LABEL
            return original_department(role)

        staff._department = department_with_giamdoc
        staff._giamdoc_department_installed = True

    # Giám đốc sorts before the existing employee-role order, without changing
    # the relative order of any existing role.
    staff_sort.ROLE_RANK[GIAMDOC_ROLE] = -1

    # Nội quy can now use either the internal key `giamdoc` or the visible label
    # `Giám đốc` in the "User có quyền được nhập" / exception columns.
    leave_rules.role_tokens = _add_role_token(leave_rules.role_tokens, leave_rules.norm)

    # The legacy Web V2 API has its own compatible parser. Patch it after the
    # shared API has finished importing so all subsequent route installers see it.
    try:
        import vera_web_v2_api_shared as shared

        api = shared._api
        api._role_tokens = _add_role_token(api._role_tokens, api._norm)
    except Exception:
        # Role creation/permissions must still work even if this optional parser
        # cannot be patched during a non-API import (for example isolated tests).
        pass


def install_work_schedule_permissions() -> None:
    group = permissions.FEATURE_GROUPS.setdefault("Lịch làm việc", {})
    group.update(WORK_SCHEDULE_PERMISSION_GROUP)
    permissions.FEATURES.update(WORK_SCHEDULE_PERMISSION_GROUP)

    # Defaults: Quản lý can arrange all three groups; Lễ tân and Locker can see
    # their own group. Admin already receives set(FEATURES) dynamically through
    # the permission resolver and remains unrestricted.
    permissions.DEFAULT_ROLE_FEATURES.setdefault("quanly", set()).update(WORK_SCHEDULE_PERMISSION_GROUP)
    permissions.DEFAULT_ROLE_FEATURES.setdefault("letan", set()).add("work_schedule_letan")
    permissions.DEFAULT_ROLE_FEATURES.setdefault("locker", set()).add("work_schedule_locker")

    _install_giamdoc_role()

    # Global Web V2 directory visibility rule. It affects employee/account lists
    # across pages while deliberately preserving historical transaction records.
    _install_directory_visibility_middleware()
