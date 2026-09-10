from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "web-v2/src/lib/searchableDropdowns.js"


def test_all_native_dropdowns_use_the_shared_search_menu():
    source = SOURCE.read_text(encoding="utf-8")
    main = (ROOT / "web-v2/src/main.jsx").read_text(encoding="utf-8")
    assert "startSearchableDropdowns()" in main
    assert "win.HTMLSelectElement.prototype" in source
    assert "source.dispatchEvent(new win.Event('change', { bubbles: true }))" in source
    assert "input.type = 'search'" in source
    assert "dropdownOptions(active.source, active.input.value)" in source
    assert "event.key === 'Escape'" in source
    assert "'ArrowDown', 'ArrowUp'" in source


def test_employee_list_rows_keep_native_selects_for_safe_react_filtering():
    source = SOURCE.read_text(encoding="utf-8")
    assert "doc.body).appendChild(menu)" in source
    assert "insertAdjacentElement" not in source
    assert "source.remove()" not in source
    assert "observer.disconnect()" in source
