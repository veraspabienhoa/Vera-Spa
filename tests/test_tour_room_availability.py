from datetime import datetime, timedelta, timezone
from pathlib import Path

from openpyxl import Workbook

from vera_web_v2_people import _available_rooms_for_tour, _prepare_tour, _room_snapshot


ROOT = Path(__file__).resolve().parents[1]


def test_room_is_not_available_when_any_slot_is_doing_or_waiting():
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Room"
    sheet.append(["Listofroom"] * 7)
    sheet.append([1, "Number", "Phòng", "", "", "", ""])
    sheet.append([2, 1.1, 1, "Body 90", "Nhân viên A", "ĐANG THỰC HIỆN", 20])
    sheet.append([3, 1.2, 1, "", "#N/A", "#N/A", "#N/A"])
    sheet.append([4, 2.1, 2, "Body 60", "Nhân viên B", "ĐANG CHỜ", ""])
    sheet.append([5, 2.2, 2, "", "#N/A", "#N/A", "#N/A"])
    sheet.append([6, 3.1, 3, "", "#N/A", "#N/A", "#N/A"])
    sheet.append([7, 3.2, 3, "", "#N/A", "#N/A", "#N/A"])
    sheet.append([8, 4.1, 4, "Dữ liệu cũ", "Nhân viên cũ", "", ""])

    result = _room_snapshot(sheet)

    assert result["occupied"] == ["1", "2"]
    assert result["available"] == ["3", "4"]
    assert result["available_count"] == 2

    workbook.close()


def test_room_is_not_available_when_it_appears_in_web_tour_room_column():
    rooms = {"available": ["1", "2", "3", "VIP"]}
    prepared = {
        "columns": ["STT", "Tên nhân viên", "PHÒNG"],
        "records": [
            {"STT": 1, "Tên nhân viên": "A", "PHÒNG": 2},
            {"STT": 2, "Tên nhân viên": "B", "PHÒNG": "Phòng VIP"},
            {"STT": 3, "Tên nhân viên": "C", "PHÒNG": ""},
        ],
    }

    assert _available_rooms_for_tour(rooms, prepared) == ["1", "3"]


def test_tour_record_exposes_exact_countdown_deadline_for_room_clock():
    vn_tz = timezone(timedelta(hours=7))
    now = datetime(2026, 9, 5, 12, 0, tzinfo=vn_tz)
    columns = [
        "STT", "Tên nhân viên", "Trạng thái", "Phòng", "Đi làm", "Vào ca",
        "Yêu cầu", "Thời lượng", "TG bắt đầu thực hiện",
    ]
    source = [{
        "STT": 1,
        "Tên nhân viên": "Nhân viên A",
        "Trạng thái": "Đang thực hiện",
        "Phòng": 16,
        "Đi làm": "Đi làm",
        "Vào ca": "Ca 1",
        "Yêu cầu": "",
        "Thời lượng": 60,
        "TG bắt đầu thực hiện": "05/09/2026 11:40:00",
    }]

    record = _prepare_tour(columns, source, now)["records"][0]

    assert record["TG CÒN LẠI"] == 40
    assert datetime.fromisoformat(record["_countdown_deadline"]) == datetime(2026, 9, 5, 12, 40, tzinfo=vn_tz)


def test_desktop_employee_table_expands_to_show_all_rows():
    source = (ROOT / "web-v2/src/pages/TourPage.jsx").read_text(encoding="utf-8")

    assert ".tour-records-panel .tour-table{max-height:none;overflow-x:auto;overflow-y:visible}" in source
    assert ".tour-records-panel .tour-table{max-height:calc(100vh" not in source


def test_tour_heading_and_available_room_summary_are_compact():
    source = (ROOT / "web-v2/src/pages/TourPage.jsx").read_text(encoding="utf-8")

    assert "<span className=\"eyebrow\"><Compass" not in source
    assert ".tour-heading-title h1{margin:3px 0 0;color:var(--green-950);font-family:Georgia,serif;font-size:18px" in source
    assert "}.tour-heading-title h1{font-size:14.5px}" in source
    assert ")).length} phòng đang trống</small>" in source
    assert ")).length}/{displayedRooms.length} phòng đang trống" not in source
    assert "grid-template-columns:minmax(520px,1fr) minmax(330px,.62fr)" in source
    assert ".tour-room-panel-head small{justify-self:center" in source


def test_tour_metric_boxes_follow_the_requested_two_row_order():
    source = (ROOT / "web-v2/src/pages/TourPage.jsx").read_text(encoding="utf-8")
    labels = (
        "Có thể lên tua", "Đang thực hiện", "Số nhân viên", "Nghỉ phép",
        "Sắp xong", "Đang chờ", "Đi làm", "Nghỉ giữa Ca",
    )

    positions = [source.index(f"label: '{label}'") for label in labels]
    assert positions == sorted(positions)
    assert 'className="tour-customer-count"' not in source


def test_desktop_employee_header_stays_fixed_without_vertical_table_scroll():
    source = (ROOT / "web-v2/src/pages/TourPage.jsx").read_text(encoding="utf-8")

    assert "--tour-table-head-offset" in source
    assert "stickyRect.bottom + 4 - tableRect.top" in source
    assert "ref={recordsTableRef}" in source
    assert ".tour-records-panel .tour-table{max-height:none" in source
