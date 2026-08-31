from datetime import datetime

from vera_web_v2_attendance_policy_patch import _completed_tour_covers_timesoft_open


def test_completed_tour_pair_clears_timesoft_summary_open_event_inside_interval():
    tour_out = datetime(2026, 8, 31, 17, 24, 11)
    tour_in = datetime(2026, 8, 31, 18, 16, 54)
    timesoft_summary_last = datetime(2026, 8, 31, 18, 0, 21)
    assert _completed_tour_covers_timesoft_open(timesoft_summary_last, tour_out, tour_in)


def test_completed_tour_pair_does_not_hide_new_break_after_previous_return():
    tour_out = datetime(2026, 8, 31, 17, 24, 11)
    tour_in = datetime(2026, 8, 31, 18, 16, 54)
    new_break = datetime(2026, 8, 31, 20, 0, 0)
    assert not _completed_tour_covers_timesoft_open(new_break, tour_out, tour_in)
