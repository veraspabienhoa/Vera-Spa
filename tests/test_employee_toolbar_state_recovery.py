from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_employee_toolbar_uses_single_react_filter_source():
    source = (ROOT / "web-v2/src/lib/employeeToolbarRecovery.js").read_text(encoding="utf-8")

    assert "forceReactControlValue" in source
    assert "veraToolbarStateSynced" in source
    assert "select.classList.remove('vera-typing-select-source')" in source
    assert "select.dataset.veraTypingSearch = '1'" in source
    assert "hideDuplicateListSearch" in source
    assert "wrapper.style.setProperty('display', 'none', 'important')" in source
    assert "resyncToolbarAfterNativeChange" in source
    assert "document.addEventListener('change'" in source
