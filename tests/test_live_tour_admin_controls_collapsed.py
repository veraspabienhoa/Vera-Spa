from ui_source import read_ui_source
from pathlib import Path


def test_admin_live_tour_controls_are_collapsed_until_requested():
    source = read_ui_source(Path("web-v2/src/pages/LiveTourPage.jsx"))
    css = Path("web-v2/src/pages/LiveTourControls.css").read_text(encoding="utf-8")

    assert "const [adminControlsVisible, setAdminControlsVisible] = useState(false)" in source
    assert "{isAdmin && <div className=\"live-tour-admin-controls-toggle\">" in source
    assert "adminControlsVisible ? 'Ẩn điều khiển' : 'Hiện điều khiển'" in source
    assert "{(!isAdmin || adminControlsVisible) && <section" in source
    assert 'id="live-tour-admin-controls"' in source
    assert 'aria-expanded={adminControlsVisible}' in source
    quick_tools = source.index('<div className="tour-quick-tools">')
    toggle = source.index('<div className="live-tour-admin-controls-toggle">')
    controls = source.index('<section id="live-tour-admin-controls"')
    assert quick_tools < toggle < controls
    assert "ADMIN_LIVE_TOUR_CONTROLS_COLLAPSED_V1" in css
