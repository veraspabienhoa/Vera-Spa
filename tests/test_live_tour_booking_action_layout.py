from pathlib import Path


def test_live_tour_booking_actions_are_wider_and_more_spaced():
    dialog = Path("web-v2/src/components/LiveTourBookingDialog.jsx").read_text(encoding="utf-8")
    page = Path("web-v2/src/pages/LiveTourPage.jsx").read_text(encoding="utf-8")

    assert "tour-booking-submit-actions" in dialog
    assert ".tour-booking-submit-actions{gap:21px}" in page
    assert ".tour-booking-submit-actions>button{flex:1 1 0;min-width:0}" in page
    assert ".tour-booking-submit-actions>.primary-button[type=submit]{flex-grow:3}" in page
