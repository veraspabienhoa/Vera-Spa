from pathlib import Path


def test_permission_dependency_closure_covers_major_feature_groups():
    source = Path("vera_web_v2_permissions.py").read_text(encoding="utf-8")

    expected = {
        '"tour_refresh": {"tour"}',
        '"live_tour_booking": {"live_tour_view"}',
        '"live_tour_paid_invoice_edit": {"live_tour_paid_invoice_view"}',
        '"leave_manage_edit": {"leave_manage"}',
        '"long_leave_approve": {"long_leave", "long_leave_stats"}',
        '"employee_add_save": {"staff_list", "employee_add"}',
        '"ktv_shift_edit": {"ktv_shift_view"}',
        '"contract_1_template_edit": {"contract_1_view"}',
        '"official_rules_edit": {"official_rules_view"}',
        '"payroll_history_edit": {"payroll", "payroll_history"}',
        '"snapshot_export": {"snapshot_today"}',
        '"sync_postgres": {"sync"}',
        '"column_config_edit": {"column_config"}',
        '"storage_delete": {"storage_admin_view"}',
        '"revenue_entry_create": {"revenue_view"}',
        '"revenue_tip_edit": {"revenue_view"}',
    }
    for marker in expected:
        assert marker in source

    assert "def permission_closure(" in source
    assert "allowed = permission_closure(set(body.allowed_features))" in source
    assert '"dependencies": {key: sorted(value)' in source


def test_permissions_ui_auto_enables_prerequisites_and_disables_dependents():
    source = Path("web-v2/src/pages/PermissionsPage.jsx").read_text(encoding="utf-8")

    assert "const expandDependencies = (features, source = data) =>" in source
    assert "const dependentFeatures = (feature, source = data) =>" in source
    assert "return expandDependencies([...current, feature])" in source
    assert "const blocked = new Set([feature, ...dependentFeatures(feature)])" in source
    assert "const normalizedAllowed = inherit ? allowed : expandDependencies(allowed)" in source
    assert "Quyền phụ thuộc được tự động đồng bộ" in source
