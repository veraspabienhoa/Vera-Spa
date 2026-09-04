from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_update_accepts_postgres_only_auto_check_rows():
    source = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    route = source.split('@app.patch("/v2/leave/records/{record_uid}")', 1)[1].split(
        "def _delete_leave_uids", 1
    )[0]

    assert "Bản ghi không có vị trí MainData hợp lệ" not in route
    assert "has_main_mirror" in route
    assert "if has_main_mirror or rebalanced:" in route
    assert "if has_main_mirror:" in route
    assert "Bản ghi PostgreSQL không có dòng MainData cần đồng bộ." in route
    assert '_update_record(conn, record, source_row, str(old.get("source_sheet_id") or ""))' in route


def test_admin_edit_bypasses_catalog_role_day_and_timing_rules():
    source = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    guard = source.split("def _validate_edit_permission", 1)[1].split(
        "def _validate_and_prepare", 1
    )[0]

    admin_at = guard.index('if role == "admin":')
    catalog_at = guard.index("_catalog_rule_for_edit")
    assert admin_at < catalog_at
    assert "return _reason_item(conn, new_reason), True" in guard


def test_admin_is_not_blocked_by_monthly_weekend_limit():
    source = (ROOT / "vera_leave_registration_live_shared.py").read_text(encoding="utf-8")
    assert "if not is_admin and not (is_annual_range_reason or is_long_sick_range_reason):" in source


def test_admin_can_edit_history_for_an_inactive_employee():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    shared = (ROOT / "vera_web_v2_api_shared.py").read_text(encoding="utf-8")
    assert 'allow_inactive_employee=(ident.role == "admin")' in api
    assert "CAST(:allow_inactive AS boolean)" in shared


def test_type_column_is_display_only_and_never_disables_reason_controls():
    source = (ROOT / "web-v2/src/pages/LeaveListTypeColumn.jsx").read_text(encoding="utf-8")
    assert "Display-only enhancement" in source
    assert "option.hidden" not in source
    assert "option.disabled" not in source
    assert "select.disabled" not in source
    assert "letan-three-choice-select" not in source
