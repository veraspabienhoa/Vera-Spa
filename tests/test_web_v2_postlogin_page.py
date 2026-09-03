from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_postlogin_opens_leave_page_instead_of_tour_for_privileged_roles():
    source = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")

    assert "TOUR_DEFAULT_ROLES" not in source
    assert "setPage(me.must_change_password ? 'profile' : 'leave')" in source

