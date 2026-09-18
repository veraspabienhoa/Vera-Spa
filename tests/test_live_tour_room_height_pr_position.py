from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_live_tour_room_height_is_fifteen_percent_taller_and_pr_uses_marked_lower_area():
    overrides = (ROOT / "web-v2/src/live-tour-mobile-overrides.css").read_text(encoding="utf-8")
    appearance = (ROOT / "web-v2/src/lib/liveTourAppearance.js").read_text(encoding="utf-8")

    assert "LIVE_TOUR_ROOM_HEIGHT_PR_POSITION_V3" in overrides
    assert "grid-auto-rows: 110.4px !important" in overrides
    assert "height: 110.4px !important" in overrides
    assert "min-height: 110.4px !important" in overrides
    assert "max-height: 110.4px !important" in overrides

    assert ".tour-room-card.has-private-service .tour-room-booking-button" in overrides
    assert "position: static !important" in overrides
    assert "right: 9% !important" in overrides
    assert "bottom: 6px !important" in overrides
    assert "bottom: 5px !important" in overrides

    assert "roomHeight > 0 ? roomHeight : 110.4" in appearance
