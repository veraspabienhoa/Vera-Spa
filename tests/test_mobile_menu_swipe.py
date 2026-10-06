from pathlib import Path


def test_app_shell_supports_touch_swipe_menu_open_and_close():
    source = Path("web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")

    assert "const menuSwipeRef = useRef(null)" in source
    assert "event.pointerType !== 'touch'" in source
    assert "Math.abs(dx) >= 70" in source
    assert "gesture.startX <= 48" in source
    assert "setMobileOpen(true)" in source
    assert "setStandaloneMenuOpen(true)" in source
    assert "gesture.sidebarWasOpen && dx < 0" in source
    assert "setMobileOpen(false)" in source
    assert "setStandaloneMenuOpen(false)" in source
    assert "onPointerDown={beginMenuSwipe}" in source
    assert "onPointerUp={endMenuSwipe}" in source
    assert "onPointerCancel={cancelMenuSwipe}" in source
