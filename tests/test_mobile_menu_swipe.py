from pathlib import Path


def test_app_shell_supports_touch_swipe_menu_open_and_close():
    # The behavior is exercised in web-v2/tests/menuWipe.test.mjs. Keep this
    # integration guard for normal and standalone shells and the CI entrypoint.
    source = Path('web-v2/src/components/AppShell.jsx').read_text(encoding='utf-8')
    workflow = Path('.github/workflows/ci.yml').read_text(encoding='utf-8')
    assert "import useMenuWipe from '../lib/useMenuWipe'" in source
    assert 'ref={shellRef}' in source
    assert 'useMenuWipe(shellRef, sidebarOpen, value =>' in source
    assert 'if (standalone) setStandaloneMenuOpen(value)' in source
    assert 'else setMobileOpen(value)' in source
    assert "sidebarOpen ? 'mobile-menu-open'" in source
    assert 'node --test tests/menuWipe.test.mjs' in workflow
