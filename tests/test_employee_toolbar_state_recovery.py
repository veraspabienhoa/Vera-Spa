from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_employee_toolbar_uses_single_react_filter_source():
    source = (ROOT / "web-v2/src/lib/employeeToolbarRecovery.js").read_text(encoding="utf-8")
    directory = (ROOT / "web-v2/src/lib/employeeDirectoryUx.js").read_text(encoding="utf-8")

    assert "veraToolbarStateSynced" in source
    assert "select.classList.remove('vera-typing-select-source')" in source
    assert "select.dataset.veraTypingSearch = '1'" in source
    assert "removeDuplicateListSearch" in source
    assert "wrapper?.remove()" in source
    assert "forceReactControlValue" not in source
    assert "dispatchEvent(new Event('input'" not in source
    assert "panel?.querySelector('.vera-list-name-search')?.remove()" in directory
    assert "wrap.innerHTML" not in directory
