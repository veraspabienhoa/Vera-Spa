from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web-v2/src/lib/employeeDirectoryUx.js"


def test_employee_dropdowns_use_native_select_setter_for_react_state():
    source = SOURCE.read_text(encoding="utf-8")
    assert "HTMLSelectElement.prototype" in source
    assert "setNativeValue(select, row.value)" in source
    assert "new Event('change', { bubbles: true })" in source


def test_employee_dropdowns_use_cross_browser_search_menu_not_datalist():
    source = SOURCE.read_text(encoding="utf-8")
    assert "input.type = 'search'" in source
    assert "vera-typing-menu" in source
    assert "filteredRows(select, query)" in source
    assert "searchKey(row.label).includes(key)" in source
    assert "document.createElement('datalist')" not in source


def test_employee_dropdown_menu_supports_mouse_and_keyboard_selection():
    source = SOURCE.read_text(encoding="utf-8")
    assert "button.addEventListener('click'" in source
    assert "event.key !== 'Enter'" in source
    assert "event.key === 'Escape'" in source
    assert "event.key === 'ArrowDown'" in source


def test_employee_list_rows_keep_native_selects_for_safe_react_filtering():
    source = SOURCE.read_text(encoding="utf-8")
    guard = "if (select.closest('.staff-list-panel')) return"
    assert guard in source
    assert source.index(guard) < source.index("if (select.dataset.veraTypingSearch === '1')")
