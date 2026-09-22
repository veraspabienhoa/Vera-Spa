from pathlib import Path


def test_employee_management_does_not_inject_portal_host_into_react_tree():
    source = Path("web-v2/src/pages/EmployeeManagementEnhancements.jsx").read_text(encoding="utf-8")

    assert "createPortal" not in source
    assert "appendChild(host)" not in source
    assert "data-shift-break-settings-host" not in source
    assert "return <>" in source
    assert "<KtvShiftSettingsPanel" not in source
    assert "<ShiftBreakSettingsPanel" not in source
    settings = Path("web-v2/src/pages/SettingsPage.jsx").read_text(encoding="utf-8")
    assert "<KtvShiftSettingsPanel />" in settings
    assert "<ShiftBreakSettingsPanel />" in settings
    assert "<DepartmentShiftSettingsPanel />" in settings
