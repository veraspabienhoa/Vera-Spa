from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

def test_live_tour_rooms_have_fixed_height_and_density_fit():
    css = (ROOT / "web-v2/src/pages/LiveTourControls.css").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")
    assert "grid-auto-rows:96px!important" in css
    assert "height:96px!important;min-height:96px!important;max-height:96px!important" in css
    assert "data-room-density={Math.min(records.length, 6)}" in page
    assert "data-room-density=\"6\"" in css

def test_mobile_heading_actions_are_fifteen_percent_taller():
    css = (ROOT / "web-v2/src/pages/LiveTourControls.css").read_text(encoding="utf-8")
    assert "min-height:16.56px!important" in css

def test_all_rooms_clears_room_employee_filters():
    page = (ROOT / "web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")
    marker = "setRoomSegment('all'); setSelectedRoomKey(''); setRoomFilterIds(new Set()); setSelectedIds(new Set()); setEmployeePickId(''); setEmployeeSearch(''); setActiveFilter('all')"
    assert marker in page
