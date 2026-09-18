from pathlib import Path


def test_admin_live_tour_controls_are_collapsed_until_requested():
    source = Path("web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")
    css = Path("web-v2/src/pages/LiveTourControls.css").read_text(encoding="utf-8")

    assert "const [adminControlsVisible, setAdminControlsVisible] = useState(false)" in source
    assert "{isAdmin && <div className=\"live-tour-admin-controls-toggle\">" in source
    assert "adminControlsVisible ? 'Ẩn điều khiển' : 'Hiện điều khiển'" in source
    assert "{(!isAdmin || adminControlsVisible) && <section" in source
    assert 'id="live-tour-admin-controls"' in source
    assert 'aria-expanded={adminControlsVisible}' in source
    assert "ADMIN_LIVE_TOUR_CONTROLS_COLLAPSED_V1" in css
