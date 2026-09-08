"""Exercise PATCH -> installed policy -> shared validator with isolated storage."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest
from fastapi import FastAPI, HTTPException

import vera_leave_registration_shared as canonical_rules
import vera_web_v2_api as api
import vera_web_v2_api_shared as shared
import vera_web_v2_letan_leave_guard as guard
import vera_web_v2_policy_v39 as policy_v39
from vera_employee_self_service_policy import normalize_policy as employee_policy
from vera_letan_leave_policy import normalize_policy as editor_policy


TODAY = date(2026, 9, 8)
EMPLOYEE_ROLES = ("nhanvien", "leader", "locker", "tapvu")
ALL_ROLES = ("admin", "letan", "quanly", *EMPLOYEE_ROLES)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):
        return cls(2026, 9, 8, 12, tzinfo=api.VN_TZ).astimezone(tz or api.VN_TZ)


class Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def first(self):
        return self.rows[0] if self.rows else None

    def all(self):
        return self.rows


class Storage:
    """Only persistence/configuration is replaced; permission rules execute."""
    def __init__(self):
        self.row = {
            "record_uid": "leave-1", "source_sheet_id": "", "source_row": 0,
            "leave_date": TODAY, "employee_name": "Thiên Kim",
            "leave_reason": "Nghỉ CÓ phép", "leave_type": "Có phép",
            "calculated_days": 1.0, "detail": "", "accumulated_leave": 1.0,
        }
        self.active = True
        self.has_permission = True
        self.employee_policy = employee_policy(None)
        self.editor_policy = editor_policy(None)
        self.start = date(2026, 1, 1)
        self.history = []
        self.saved = None
        self.committed = False
        self.rolled_back = False
        self.is_active = True
        self.employee_checks = []
        self.excluded_uids = []

    def connect(self):
        return self

    def begin(self):
        return self

    def commit(self):
        self.committed = True
        self.is_active = False

    def rollback(self):
        self.rolled_back = True
        self.is_active = False

    def close(self):
        pass

    def execute(self, statement, params=None):
        sql = str(statement)
        params = params or {}
        if "pg_advisory_xact_lock" in sql:
            return Result([])
        if "FOR UPDATE" in sql:
            return Result([dict(self.row)] if params["uid"] == self.row["record_uid"] else [])
        if "FROM employees" in sql:
            if "employment_start_date" in sql:
                return Result([{"employment_start_date": self.start, "payload": {}}])
            self.employee_checks.append(params["allow_inactive"])
            if not self.active and not params["allow_inactive"]:
                return Result([])
            return Result([{
                "username": self.row["employee_name"], "monthly_generated": 5,
                "monthly_leave": 5, "annual_leave": 12,
            }])
        if "FROM leave_records" in sql:
            self.excluded_uids.append(params["uid"])
            return Result([
                row for row in [self.row, *self.history]
                if row["record_uid"] != params["uid"]
            ])
        raise AssertionError(f"Unexpected storage query: {sql}")


@pytest.fixture
def runtime(monkeypatch):
    storage = Storage()
    for module in (api, shared, guard, canonical_rules):
        monkeypatch.setattr(module, "datetime", Clock)

    # Track installer mutations so each test starts with the original chain.
    for module, name in (
        (api, "_validate_and_prepare"), (shared, "_validate_and_prepare"),
        (api, "_validate_edit_permission"), (api, "_validate_delete_permission"),
        (shared, "validate_leave_registration_request_live"),
    ):
        monkeypatch.setattr(module, name, getattr(module, name))
    monkeypatch.setattr(shared, "_admin_leave_unrestricted_installed", False, raising=False)

    def reason_item(conn, reason):
        unpaid = "khong phep" in api._norm(reason)
        return {
            "name": reason, "leave_type": "Không phép" if unpaid else "Có phép",
            "days": 0.5 if "ve som" in api._norm(reason) else 1.0,
            "penalty": 0, "requires_manual_penalty": False,
            "allowed_roles": "", "allowed_days": "",
            "register_type": "Không giới hạn", "cancel_type": "Không giới hạn",
        }

    for module in (api, shared):
        monkeypatch.setattr(module, "_reason_item", reason_item)
        monkeypatch.setattr(module, "load_employee_self_service_policy", lambda conn: storage.employee_policy)
    monkeypatch.setattr(guard, "load_letan_leave_policy", lambda conn: storage.editor_policy)
    monkeypatch.setattr(api, "_engine_instance", lambda: storage)
    monkeypatch.setattr(api, "_has_any_feature", lambda *args: storage.has_permission)
    monkeypatch.setattr(api, "_feature_allowed", lambda *args: storage.has_permission)
    monkeypatch.setattr(api, "_rebalance_progressive_rows", lambda *args: [])
    monkeypatch.setattr(api, "_update_record", lambda conn, record, *args: setattr(storage, "saved", record))
    monkeypatch.setattr(shared, "load_weekend_unpaid_enabled", lambda conn: False)
    monkeypatch.setattr(shared, "_daily_quota_config", lambda: {
        "days": [{"paid_limit": 50, "generated_limit": 50} for _ in range(7)],
    })

    def live_rows(conn, exclude_record_uid=""):
        storage.excluded_uids.append(exclude_record_uid)
        return pd.DataFrame([
            {
                "Ngày": row["leave_date"], "Tên nhân viên": row["employee_name"],
                "Lý do nghỉ": row["leave_reason"], "Loại nghỉ": row["leave_type"],
                "Số ngày tính": row["calculated_days"],
            }
            for row in [storage.row, *storage.history]
            if row["record_uid"] != exclude_record_uid
        ], columns=["Ngày", "Tên nhân viên", "Lý do nghỉ", "Loại nghỉ", "Số ngày tính"])

    monkeypatch.setattr(shared, "_live_leave_df", live_rows)
    app = FastAPI()
    app.patch("/v2/staff/{username}")(lambda username: {})
    policy_v39.install_policy_v39(
        app, engine_instance=lambda: storage, current_identity=lambda: None,
        require_feature=lambda *args: None, vn_tz=api.VN_TZ,
    )
    guard.install_letan_leave_guard(app, api_module=api, vn_tz=api.VN_TZ)
    return storage


def edit(storage, role, *, reason="Về sớm CÓ phép", own=True):
    ident = SimpleNamespace(role=role, employee_username=storage.row["employee_name"] if own else "Người khác")
    return api.update_leave(storage.row["record_uid"], api.LeaveUpdate(leave_reason=reason), ident)


@pytest.mark.parametrize("role", ALL_ROLES)
def test_allowed_edit_reaches_shared_validator_and_commits(runtime, role):
    if role in EMPLOYEE_ROLES:
        runtime.row["leave_date"] = TODAY + timedelta(days=3)
    response = edit(runtime, role)
    assert response["ok"] is True
    assert runtime.committed is True
    assert runtime.saved["record_uid"] == "leave-1"
    assert runtime.saved["leave_reason"] == "Về sớm CÓ phép"
    assert runtime.saved["calculated_days"] == 0.5
    assert runtime.saved["accumulated_leave"] == 0.5
    assert runtime.employee_checks == [role == "admin"]
    assert set(runtime.excluded_uids) == {"leave-1"}


@pytest.mark.parametrize("offset", (-365, 0, 365))
def test_admin_edits_inactive_employee_at_any_date(runtime, offset):
    runtime.active = False
    runtime.has_permission = False
    runtime.row["leave_date"] = TODAY + timedelta(days=offset)
    assert edit(runtime, "admin")["ok"] is True
    assert runtime.committed
    assert runtime.employee_checks == [True]


@pytest.mark.parametrize("role", ("letan", "quanly", *EMPLOYEE_ROLES))
def test_non_admin_cannot_edit_inactive_employee(runtime, role):
    runtime.active = False
    runtime.row["leave_date"] = TODAY + timedelta(days=3)
    with pytest.raises(HTTPException) as exc:
        edit(runtime, role)
    assert exc.value.status_code == 400
    assert "đang hoạt động" in exc.value.detail
    assert runtime.rolled_back and not runtime.committed


@pytest.mark.parametrize("role", ("letan", "quanly"))
def test_editor_same_day_group_exception_still_applies(runtime, role):
    runtime.has_permission = False
    assert edit(runtime, role)["ok"] is True
    with pytest.raises(HTTPException) as exc:
        api._validate_delete_permission(runtime, runtime.row, SimpleNamespace(role=role))
    assert exc.value.status_code == 403


@pytest.mark.parametrize("role", ("letan", "quanly"))
@pytest.mark.parametrize("past", (False, True))
def test_editor_cannot_cross_group_or_edit_past(runtime, role, past):
    if past:
        runtime.row["leave_date"] = TODAY - timedelta(days=1)
    with pytest.raises(HTTPException) as exc:
        edit(runtime, role, reason="Nghỉ KHÔNG phép")
    assert exc.value.status_code == 403
    assert runtime.saved is None and runtime.rolled_back


@pytest.mark.parametrize("role", EMPLOYEE_ROLES)
@pytest.mark.parametrize("own,notice_days", ((False, 3), (True, 2)))
def test_employee_ownership_and_notice_remain_enforced(runtime, role, own, notice_days):
    runtime.row["leave_date"] = TODAY + timedelta(days=notice_days)
    with pytest.raises(HTTPException) as exc:
        edit(runtime, role, own=own)
    assert exc.value.status_code == 403
    assert runtime.saved is None and runtime.rolled_back


@pytest.mark.parametrize("used,status", ((2.5, 200), (3.0, 400)))
def test_late_month_cap_counts_replacement_without_counting_old_row(runtime, used, status):
    runtime.row["leave_date"] = date(2026, 9, 22)
    runtime.start = date(2026, 9, 16)
    runtime.history = [{
        **runtime.row, "record_uid": "earlier-leave", "leave_date": date(2026, 9, 17),
        "calculated_days": used,
    }]
    if status == 200:
        assert edit(runtime, "nhanvien")["ok"] is True
        assert runtime.committed
    else:
        with pytest.raises(HTTPException) as exc:
            edit(runtime, "nhanvien")
        assert exc.value.status_code == status
        assert "tối đa 3 ngày" in exc.value.detail
        assert runtime.saved is None and runtime.rolled_back
    assert set(runtime.excluded_uids) == {"leave-1"}


def test_create_style_call_keeps_inactive_employee_blocked_by_default(runtime):
    runtime.active = False
    body = api.LeaveCreate(
        employee_name=runtime.row["employee_name"], leave_date=TODAY,
        leave_reason="Nghỉ CÓ phép",
    )
    with pytest.raises(HTTPException) as exc:
        shared._validate_and_prepare(runtime, body, SimpleNamespace(role="admin", employee_username="admin"))
    assert exc.value.status_code == 400
    assert runtime.employee_checks == [False]
