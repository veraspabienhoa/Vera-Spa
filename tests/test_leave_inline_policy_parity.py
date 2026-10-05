"""Verify inline reason choices against the installed server permission guards."""
from datetime import date, datetime, timedelta
from types import SimpleNamespace
import json
from pathlib import Path
import subprocess

from fastapi import FastAPI, HTTPException
import pytest

import vera_web_v2_api as api
import vera_web_v2_letan_leave_guard as guard
from vera_letan_leave_policy import normalize_policy

TODAY = date(2026, 9, 11)
GROUPS = normalize_policy(None)["groups"]


@pytest.fixture
def permissions(monkeypatch):
    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return cls(2026, 9, 11, 12, tzinfo=tz)

    def item(_conn, reason):
        return {"name": reason, "leave_type": "Không phép" if "KHÔNG phép" in reason else "Có phép",
                "days": 1, "allowed_roles": "", "allowed_days": "", "cancel_type": "Không giới hạn"}

    monkeypatch.setattr(api, "datetime", Clock)
    monkeypatch.setattr(guard, "datetime", Clock)
    monkeypatch.setattr(api, "_reason_item", item)
    monkeypatch.setattr(api, "_has_any_feature", lambda conn, ident, features: ident.allowed)
    monkeypatch.setattr(api, "_feature_allowed", lambda *args: False)
    monkeypatch.setattr(api, "_registration_rule", lambda *args: None)
    monkeypatch.setattr(api, "load_employee_self_service_policy", lambda conn: {"enabled": True, "regular_notice_days": 3, "unpaid_notice_days": 1})
    monkeypatch.setattr(guard, "load_letan_leave_policy", lambda conn: normalize_policy(None))
    # The UI fix must keep existing guards; install them around the real helpers.
    monkeypatch.setattr(guard, "_install_admin_unrestricted_validator", lambda: None)
    monkeypatch.setattr(guard, "_install_admin_reason_catalog", lambda *args: None)
    module = SimpleNamespace(**vars(api))
    guard.install_letan_leave_guard(FastAPI(), api_module=module, vn_tz=api.VN_TZ)
    return module


def allowed(call):
    try:
        call()
        return True
    except HTTPException as exc:
        assert exc.status_code in {400, 403}
        return False


def record(offset=0, reason="Nghỉ CÓ phép"):
    return {"leave_date": TODAY + timedelta(days=offset), "leave_reason": reason, "employee_name": "An An",
            "leave_type": "Không phép" if "KHÔNG phép" in reason else "Có phép", "calculated_days": 1}


def test_frontend_one_three_day_choices_match_server_for_all_self_service_roles(permissions):
    contexts, expected = [], []
    for role in ["nhanvien", "leader", "locker", "tapvu"]:
        for offset in [-1, 0, 1, 2, 3]:
            for own in [True, False]:
                for reason in ["Nghỉ CÓ phép", "Nghỉ KHÔNG phép"]:
                    row = record(offset)
                    ident = SimpleNamespace(role=role, employee_username="An An" if own else "Người khác", allowed=False)
                    next_reason = api._reason_item(None, reason)
                    contexts.append({"context": {"role": role, "today": TODAY.isoformat(), "recordDate": row["leave_date"].isoformat(),
                        "currentReason": row["leave_reason"], "currentLeaveType": row["leave_type"], "isOwnRecord": own,
                        "employeeSelfServicePolicy": {"enabled": True, "regular_notice_days": 3, "unpaid_notice_days": 1}}, "next": next_reason})
                    expected.append([allowed(lambda: permissions._validate_edit_permission(None, row, reason, ident)),
                                     allowed(lambda: permissions._validate_delete_permission(None, row, ident))])
    module = (Path(__file__).resolve().parents[1] / "web-v2/src/lib/leaveRecordPermissions.js").as_uri()
    js = f'import {{canChangeLeaveReason,canDeleteLeaveRecord}} from {json.dumps(module)}; import fs from "node:fs"; console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,"utf8")).map(x=>[canChangeLeaveReason(x.context,x.next),canDeleteLeaveRecord(x.context)])));'
    result = subprocess.run(["node", "--input-type=module", "-e", js], input=json.dumps(contexts), capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == expected


@pytest.mark.parametrize("role", ["letan", "quanly"])
@pytest.mark.parametrize("group", GROUPS, ids=lambda group: group["name"])
def test_today_groups_allow_only_three_reasons_and_never_delete(permissions, role, group):
    ident = SimpleNamespace(role=role, employee_username="Lễ tân", allowed=False)
    row = record(0, group["reasons"][0])
    for candidate in group["reasons"]:
        assert allowed(lambda: permissions._validate_edit_permission(None, row, candidate, ident))
    assert not allowed(lambda: permissions._validate_edit_permission(None, row, "Lý do khác", ident))
    assert not allowed(lambda: permissions._validate_delete_permission(None, row, ident))


@pytest.mark.parametrize("role", ["admin", "letan", "quanly"])
@pytest.mark.parametrize("offset", [-3, 0, 3])
@pytest.mark.parametrize("has_permission", [False, True])
def test_admin_history_and_other_reasons_follow_role_permission_rules(permissions, role, offset, has_permission):
    ident = SimpleNamespace(role=role, employee_username="Quản trị", allowed=has_permission)
    row = record(offset, "Lý do khác")
    expected = role == "admin" or (offset >= 0 and has_permission)
    assert allowed(lambda: permissions._validate_edit_permission(None, row, "Lý do khác", ident)) is expected
    assert allowed(lambda: permissions._validate_delete_permission(None, row, ident)) is expected


@pytest.mark.parametrize('role', ['letan', 'quanly'])
@pytest.mark.parametrize('offset', [-3, 0, 3])
@pytest.mark.parametrize('enabled', [True, False])
def test_created_today_grants_delete_only_for_editor_roles(permissions, monkeypatch, role, offset, enabled):
    monkeypatch.setattr(guard, 'load_letan_leave_policy', lambda conn: normalize_policy({'enabled': enabled}))
    ident = SimpleNamespace(role=role, employee_username='Người khác', allowed=False)
    row = record(offset)
    before_edit = allowed(lambda: permissions._validate_edit_permission(None, row, 'Lý do khác', ident))
    row.update(created_at=datetime(2026, 9, 11, 0, 1, tzinfo=api.VN_TZ), updated_by='Admin')
    assert allowed(lambda: permissions._validate_delete_permission(None, row, ident))
    assert allowed(lambda: api._validate_delete_permission(None, row, ident))
    assert allowed(lambda: permissions._validate_edit_permission(None, row, 'Lý do khác', ident)) == before_edit


def test_creation_timestamp_boundary_and_ui_server_delete_parity(permissions):
    contexts, expected = [], []
    for role in ['letan', 'quanly', 'admin', 'nhanvien', 'leader', 'locker', 'tapvu']:
        for created in [None, '', 'invalid', '2026-09-11T00:01:00',
                        '2026-09-10T16:59:59Z', '2026-09-10T17:00:00Z',
                        '2026-09-11T16:59:59Z', '2026-09-11T17:00:00Z']:
            for offset in [-1, 0, 3]:
                row = record(offset)
                row.update(created_at=created, update_date='11/09/2026', updated_at='2026-09-11T01:00:00Z')
                ident = SimpleNamespace(role=role, employee_username='Người khác', allowed=False)
                contexts.append({'role': role, 'recordDate': row['leave_date'].isoformat(), 'createdAt': created,
                    'currentReason': row['leave_reason'], 'currentLeaveType': row['leave_type'],
                    'today': TODAY.isoformat(), 'allowedByPermission': False, 'isOwnRecord': False})
                expected.append(allowed(lambda: permissions._validate_delete_permission(None, row, ident)))
    module = (Path(__file__).resolve().parents[1] / 'web-v2/src/lib/leaveRecordPermissions.js').as_uri()
    js = f'import {{canDeleteLeaveRecord}} from {json.dumps(module)}; import fs from "node:fs"; console.log(JSON.stringify(JSON.parse(fs.readFileSync(0,"utf8")).map(canDeleteLeaveRecord)));'
    result = subprocess.run(['node', '--input-type=module', '-e', js], input=json.dumps(contexts), capture_output=True, text=True, check=True)
    assert json.loads(result.stdout) == expected


def test_delete_and_list_queries_fetch_immutable_creation_time():
    source = (Path(__file__).resolve().parents[1] / 'vera_web_v2_api.py').read_text()
    deletion = source.split('def _delete_leave_uids(', 1)[1].split('FROM leave_records WHERE record_uid=:uid FOR UPDATE', 1)[0]
    listing = source.split('def leave_records(', 1)[1].split('FROM leave_records', 1)[0]
    assert 'created_at' in deletion and 'created_at' in listing
    page = (Path(__file__).resolve().parents[1] / 'web-v2/src/pages/LeaveRegistrationPage.jsx').read_text()
    assert 'createdAt: item?.created_at' in page


def test_batch_with_old_forbidden_record_rolls_back_before_any_delete(permissions, monkeypatch):
    today_row = {**record(), 'created_at': '2026-09-11T00:00:00+07:00'}
    old_row = {**record(), 'created_at': '2026-09-10T00:00:00+07:00', 'update_date': '11/09/2026'}
    rows = {'new': today_row, 'old': old_row}
    statements = []
    class Transaction:
        is_active = True
        rolled_back = False
        def rollback(self):
            self.rolled_back = True
            self.is_active = False
        def commit(self):
            raise AssertionError('A mixed unauthorized batch must not commit')
    tx = Transaction()
    class Connection:
        def begin(self):
            return tx
        def close(self):
            pass
        def execute(self, sql, params=None):
            statements.append(str(sql))
            if params and 'uid' in params:
                return SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: rows[params['uid']]))
            return SimpleNamespace()
    monkeypatch.setattr(api, '_engine_instance', lambda: SimpleNamespace(connect=lambda: Connection()))
    monkeypatch.setattr(api, '_validate_delete_permission', permissions._validate_delete_permission)
    with pytest.raises(HTTPException) as exc:
        api._delete_leave_uids(['new', 'old'], SimpleNamespace(role='letan', employee_username='Lễ tân', allowed=False))
    assert exc.value.status_code == 403
    assert tx.rolled_back
    assert not any('DELETE FROM' in statement for statement in statements)


@pytest.mark.parametrize("role", ["letan", "quanly", "nhanvien", "leader", "locker", "tapvu"])
@pytest.mark.parametrize("offset", [-3, 0, 3])
def test_explicit_created_today_grant_edits_and_deletes_any_employee(permissions, monkeypatch, role, offset):
    grant = lambda conn, ident, feature: feature == "leave_created_today_edit_delete"
    monkeypatch.setattr(api, "_feature_allowed", grant)
    permissions._feature_allowed = grant
    ident = SimpleNamespace(role=role, employee_username="Người khác", allowed=False)
    row = record(offset)
    row["created_at"] = "2026-09-10T17:00:00Z"
    assert allowed(lambda: permissions._validate_edit_permission(None, row, "Lý do khác", ident))
    assert allowed(lambda: permissions._validate_delete_permission(None, row, ident))
    row["created_at"] = "2026-09-10T16:59:59Z"
    if offset < 0:
        assert not allowed(lambda: permissions._validate_edit_permission(None, row, "Lý do khác", ident))
        assert not allowed(lambda: permissions._validate_delete_permission(None, row, ident))
