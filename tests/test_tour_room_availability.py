from openpyxl import Workbook

from vera_web_v2_people import _available_rooms_for_tour, _room_snapshot


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
