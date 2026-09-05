from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_postlogin_restores_each_users_last_active_page():
    source = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")

    assert "TOUR_DEFAULT_ROLES" not in source
    assert "ACTIVE_PAGE_STORAGE_PREFIX = 'vera-v2-active-page:'" in source
    assert "window.localStorage.getItem(activePageStorageKey(user))" in source
    assert "window.localStorage.setItem(activePageStorageKey(user), page)" in source
    assert "standaloneRequest.enabled ? standaloneRequest.page : readActivePage(nextSession.user)" in source
    assert "rememberActivePage(user, nextPage)" in source


def test_first_login_still_forces_profile_page():
    source = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")

    assert "me.must_change_password ? 'profile'" in source
