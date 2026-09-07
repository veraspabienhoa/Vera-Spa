from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_admin_is_unrestricted_across_shared_web_v2_leave_validation():
    guard = (ROOT / "vera_web_v2_letan_leave_guard.py").read_text(encoding="utf-8")
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")

    assert 'role != "admin"' in guard
    assert '"admin_unrestricted": True' in guard
    assert "shared_api.validate_leave_registration_request_live = admin_unrestricted_validator" in guard
    assert "_install_admin_reason_catalog(app, api_module)" in guard
    assert '"admin_reason_catalog": "all_reasons_all_dates"' in guard

    delete_guard = api.split("def _validate_delete_permission", 1)[1].split("def _validate_edit_permission", 1)[0]
    assert 'if role == "admin":' in delete_guard
    assert "return" in delete_guard

    edit_guard = api.split("def _validate_edit_permission", 1)[1].split("def _validate_and_prepare", 1)[0]
    assert 'if role == "admin":' in edit_guard
    assert "return _reason_item(conn, new_reason), True" in edit_guard


def test_letan_and_quanly_share_the_restored_edit_delete_guard():
    guard = (ROOT / "vera_web_v2_letan_leave_guard.py").read_text(encoding="utf-8")

    assert '"letan": "Lễ tân"' in guard
    assert '"quanly": "Quản lý"' in guard
    assert "if target < today:" in guard
    assert "role not in EDITOR_ROLES" in guard
    assert "new_group != old_group" in guard
    assert "target == today and _reason_group(reason, norm)" in guard
    assert "return original_edit(conn, row, new_reason, ident)" in guard
    assert "return original_delete(conn, row, ident)" in guard


def test_all_five_same_day_reason_groups_are_preserved():
    guard = (ROOT / "vera_web_v2_letan_leave_guard.py").read_text(encoding="utf-8")

    expected = (
        "Nghỉ CÓ phép",
        "Đi trễ CÓ phép",
        "Về sớm CÓ phép",
        "Nghỉ KHÔNG phép",
        "Đi trễ KHÔNG phép",
        "Về sớm KHÔNG phép",
        "Nghỉ CUỐI TUẦN CÓ phép",
        "Đi trễ CUỐI TUẦN CÓ phép",
        "Về sớm CUỐI TUẦN CÓ phép",
        "Nghỉ CUỐI TUẦN KHÔNG phép",
        "Đi trễ CUỐI TUẦN KHÔNG phép",
        "Về sớm CUỐI TUẦN KHÔNG phép",
        "Leader nghỉ phép theo chính sách",
        "Leader đi trễ sớm theo chính sách",
        "Leader về sớm về sớm theo chính sách",
    )
    assert all(reason in guard for reason in expected)
