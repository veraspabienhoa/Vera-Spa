from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_postlogin_defaults_to_live_tour_but_preserves_page_on_reverification():
    source = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")

    assert "TOUR_DEFAULT_ROLES" not in source
    navigation = (ROOT / "web-v2/src/lib/activePage.js").read_text(encoding="utf-8")
    assert "target.sessionStorage.getItem(key(user))" in navigation
    assert "target.sessionStorage.setItem(key(user), page)" in navigation
    assert "validPages.has(page) ? page : 'live-tour'" in navigation
    assert "verifiedUser.current !== nextSession.user.id" in source
    assert "standaloneRequest.enabled ? standaloneRequest.page : readNotificationPage() || readActivePage(nextSession.user, VALID_PAGES)" in source
    assert "rememberActivePage(user, nextPage, VALID_PAGES)" in source


def test_first_login_still_forces_profile_page():
    source = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")

    assert "me.must_change_password ? 'profile'" in source


def test_notification_link_only_overrides_default_for_changes():
    source = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    assert "const readNotificationPage = () => new URLSearchParams(window.location.search).get('page') === 'changes' ? 'changes' : ''" in source
