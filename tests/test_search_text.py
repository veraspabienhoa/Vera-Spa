import pytest
from vera_search_text import search_text_matches


@pytest.mark.parametrize("value,query,expected", [
    ("An An", "an an", True),
    ("Vân Anh", "an an", False),
    (["An", "an"], "An An", False),
    ("Đặng Ánh", "dang a", True),
    ("Trần An An", "an an", True),
    ("Ca 1", "ca 1", True),
    ("Combo - Body 90 phút", "body 90", True),
    ("Vân Anh", "   ", True),
])
def test_search_respects_word_boundaries(value, query, expected):
    assert search_text_matches(value, query) is expected


def test_attendance_and_export_share_the_accurate_name_filter():
    from vera_web_v2_operations_v41 import _snapshot_filter, _matches
    records = [{"employee_name": name, "break_department": "Lễ tân", "shift": "Ca 1"}
               for name in ["An An", "Vân Anh"]]
    assert [row["employee_name"] for row in _snapshot_filter(records, "an an", "le tan", "ca 1")] == ["An An"]
    assert _matches("Vân Anh", "an an") is False
