from openpyxl import Workbook

from vera_web_v2_people import _room_snapshot


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

    result = _room_snapshot(sheet)

    assert result["occupied"] == ["1", "2"]
    assert result["available"] == ["3"]
    assert result["available_count"] == 1

    workbook.close()
