from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_employee_profile_controls_are_react_owned():
    page = (ROOT / 'web-v2/src/pages/EmployeePage.jsx').read_text(encoding='utf-8')
    ux = (ROOT / 'web-v2/src/lib/employeeDirectoryUx.js').read_text(encoding='utf-8')
    assert 'staff-profile-react-actions' in page
    block = ux.split('function ensureProfileHeaderActions()', 1)[1].split('function reconcile()', 1)[0]
    assert 'appendChild' not in block
    assert 'insertBefore' not in block
    assert "querySelectorAll('.vera-profile-header-actions').forEach((node) => node.remove())" in block

def test_search_change_closes_profile_without_legacy_dom_mutation():
    page = (ROOT / 'web-v2/src/pages/EmployeePage.jsx').read_text(encoding='utf-8')
    assert 'const changeEmployeeSearch = (value) =>' in page
    assert "setProfileUser('')" in page
    assert 'onChange={changeEmployeeSearch}' in page

def test_employee_profile_has_automatic_bank_code_box():
    page = (ROOT / 'web-v2/src/pages/EmployeePage.jsx').read_text(encoding='utf-8')
    profile = (ROOT / 'web-v2/src/pages/ProfilePage.jsx').read_text(encoding='utf-8')
    for source in (page, profile):
        assert 'Mã ngân hàng tự động' in source
        assert 'VCB / ACB / TCB' in source
