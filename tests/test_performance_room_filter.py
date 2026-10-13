import vera_live_tour_query as query
import vera_web_v2_live_tour as live
from datetime import datetime, timezone


def test_employee_service_room_must_match_same_line_and_export_filter_agrees():
    rows = [{'employee_name': 'Kiều Thy', 'service': 'Body', 'room': '14.1'}, {'employee_name': 'An', 'service': 'Body', 'room': '16.1'}]
    filters = {'employee': 'kieu', 'room': '14.1'}
    assert query.matches_report({'entries': rows}, filters)
    assert not query.matches_report({'entries': rows}, {'employee': 'kieu', 'room': '16.1'})
    bounds = live._parse_export_bounds()
    bounds.update(filters)
    assert live._event_in_export_bounds(rows[0], bounds)
    assert not live._event_in_export_bounds(rows[1], bounds)
