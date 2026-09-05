from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_every_page_can_open_in_a_standalone_new_tab():
    app = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    tour = (ROOT / "web-v2/src/pages/TourPage.jsx").read_text(encoding="utf-8")

    assert "readStandalonePageRequest" in app
    assert "VALID_PAGES.has(requestedPage)" in app
    assert "standalone={standaloneRequest.enabled}" in app
    assert "url.searchParams.set('page', currentPage)" in shell
    assert "url.searchParams.set('standalone', '1')" in shell
    assert "openCurrentPageInNewTab" in shell
    assert "Mở tab mới" in shell
    assert "Mở tab riêng" not in tour
    assert "openTourInNewTab" in tour


def test_new_tab_keeps_show_and_hide_menu_controls_across_navigation():
    app = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")

    assert "url.searchParams.set('page', nextPage)" in app
    assert "url.searchParams.set('standalone', '1')" in app
    assert "standaloneRequest.enabled ? standaloneRequest.page" in app
    assert "'Ẩn Menu' : 'Hiện Menu'" in shell
