from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_employee_toolbar_uses_single_react_filter_source():
    source = (ROOT / "web-v2/src/lib/employeeToolbarRecovery.js").read_text(encoding="utf-8")
    directory = (ROOT / "web-v2/src/lib/employeeDirectoryUx.js").read_text(encoding="utf-8")

    assert "veraToolbarStateSynced" in source
    assert "toolbar.querySelectorAll('select').forEach(removeToolbarProxy)" in source
    assert "select[data-employee-name-dropdown]" in source
    assert "select.matches('[data-employee-name-dropdown]')" in directory
    assert "removeDuplicateListSearch" in source
    assert "wrapper?.remove()" in source
    assert "forceReactControlValue" not in source
    assert "dispatchEvent(new Event('input'" not in source
    assert "panel?.querySelector('.vera-list-name-search')?.remove()" in directory
    assert "wrap.innerHTML" not in directory


def test_employee_name_filter_uses_registration_style_native_dropdown():
    page = (ROOT / "web-v2/src/pages/EmployeePage.jsx").read_text(encoding="utf-8")
    assert 'className="staff-employee-name-dropdown"' in page
    assert 'data-employee-name-dropdown="true"' in page
    assert '<option value="">-- Chọn nhân viên --</option>' in page
    assert "shortEmployeeName(employee.username)" in page
    assert "const needle = searchKey(search)" in page
    assert "searchCompositionRef" not in page


def test_employee_list_does_not_duplicate_the_toolbar_name_filter():
    page = (ROOT / "web-v2/src/pages/EmployeePage.jsx").read_text(encoding="utf-8")
    heading = page.index("<h2>DANH SÁCH NHÂN VIÊN</h2>")
    actions = page.index('className="staff-list-selection-actions"', heading)

    assert heading < actions
    assert 'className="staff-search staff-list-search"' not in page
    assert page.count('data-employee-name-dropdown="true"') == 1
