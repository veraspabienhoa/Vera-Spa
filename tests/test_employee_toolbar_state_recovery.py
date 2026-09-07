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


def test_employee_search_waits_for_vietnamese_ime_composition():
    page = (ROOT / "web-v2/src/pages/EmployeePage.jsx").read_text(encoding="utf-8")
    assert "searchCompositionRef" in page
    assert "onCompositionStart" in page
    assert "onCompositionEnd={finishEmployeeSearchComposition}" in page
    assert "setAppliedSearch(search), 180" in page
    assert "const needle = searchKey(appliedSearch)" in page
