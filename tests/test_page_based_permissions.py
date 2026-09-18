from pathlib import Path


def test_permission_catalog_is_page_oriented_and_keeps_dynamic_features():
    backend = Path("vera_web_v2_permissions.py").read_text(encoding="utf-8")

    assert "PERMISSION_PAGE_LAYOUT" in backend
    assert '"id": "live-tour"' in backend
    assert '"id": "employees"' in backend
    assert '"id": "revenue"' in backend
    assert '"revenue_entry_create"' in backend
    assert '"id": "schedule"' in backend
    assert '"work_schedule_letan"' in backend
    assert '"accumulation_view"' in backend
    assert "def permission_pages()" in backend
    assert '"pages": permission_pages()' in backend
    assert "leftovers = {key: label for key, label in group.items() if key not in assigned}" in backend


def test_permissions_page_renders_each_menu_page_with_individual_actions():
    page = Path("web-v2/src/pages/PermissionsPage.jsx").read_text(encoding="utf-8")

    assert "PHÂN QUYỀN THEO TRANG" in page
    assert "Mỗi trang/menu có các tác vụ riêng" in page
    assert "const pages = useMemo" in page
    assert "permission-page-card" in page
    assert "permission-view-permission" in page
    assert "page.items.map(([key, value])" in page
    assert "onChange={() => toggle(key)}" in page
    assert "Quyền MỞ TRANG là quyền nền của menu" in page


def test_page_permissions_keep_dependency_auto_sync():
    backend = Path("vera_web_v2_permissions.py").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/PermissionsPage.jsx").read_text(encoding="utf-8")

    assert '"revenue_entry_create": {"revenue_view"}' in backend
    assert "allowed = permission_closure(set(body.allowed_features))" in backend
    assert "return expandDependencies([...current, feature])" in page
    assert "const blocked = new Set([feature, ...dependentFeatures(feature)])" in page
