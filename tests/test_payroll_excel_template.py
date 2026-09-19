from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from vera_web_v2_excel_export_style import style_workbook_bytes
from vera_web_v2_payroll import _new_payroll_workbook


FIELDS = [
    "Từ ngày",
    "Đến ngày",
    "TT",
    "Tên Hệ thống",
    "Họ và tên",
    "Tiền Lương",
    "Tiền Hỗ Trợ Hoàn Lại",
    "Hoàn trả tiền tích lũy",
    "Tích lũy",
    "Chi Phí Sinh Hoạt",
    "Tiền phạt trong tháng",
    "Vi phạm kỳ trước",
    "Tiền ứng lương",
    "Tiền hỗ trợ Locker",
    "Số tiền thực nhận",
    "Số tài khoản ngân hàng",
    "Tên ngân hàng",
]


def test_new_payroll_excel_matches_attached_template_after_global_styling():
    record = {
        "Từ ngày": "01/09/2026",
        "Đến ngày": "15/09/2026",
        "TT": 1,
        "Tên Hệ thống": "An An",
        "Họ và tên": "Đinh Thúy An",
        "Tiền Lương": 28_800_000,
        "Tiền Hỗ Trợ Hoàn Lại": 0,
        "Hoàn trả tiền tích lũy": 0,
        "Tích lũy": 0,
        "Chi Phí Sinh Hoạt": 150_000,
        "Tiền phạt trong tháng": 1_000_000,
        "Vi phạm kỳ trước": 0,
        "Tiền ứng lương": 0,
        "Tiền hỗ trợ Locker": 80_000,
        "Số tiền thực nhận": 27_570_000,
        "Số tài khoản ngân hàng": "0019074348179017",
        "Tên ngân hàng": "Ngân hàng TMCP Kỹ thương Việt Nam",
    }

    raw = _new_payroll_workbook(
        [record],
        FIELDS,
        date(2026, 9, 1),
        date(2026, 9, 15),
    )
    workbook = load_workbook(BytesIO(style_workbook_bytes(raw)))
    worksheet = workbook.active

    assert worksheet.title == "Bảng lương bản mới K1 Tháng 9"
    assert {str(item) for item in worksheet.merged_cells.ranges} == {"A1:Q1", "B2:Q2"}
    assert worksheet["A1"].value == "BẢNG LƯƠNG NHÂN VIÊN"
    assert worksheet["A2"].value == "KỲ LƯƠNG"
    assert worksheet["B2"].value == "Từ ngày 01/09/2026 đến 15/09/2026"
    assert [worksheet.cell(3, column).value for column in range(1, 18)] == FIELDS
    assert worksheet["A4"].value == "01/09/2026"
    assert worksheet.freeze_panes == "A4"
    assert worksheet.auto_filter.ref == "A3:Q4"

    for coordinate in ("A1", "A2", "B2", "A3", "Q3"):
        cell = worksheet[coordinate]
        assert cell.fill.fgColor.rgb[-6:] == "1F513F"
        assert cell.font.bold is True
        assert cell.font.color.rgb[-6:] == "FFFFFF"

    assert worksheet["F4"].number_format == "#,##0"
    assert worksheet["O4"].number_format == "#,##0"
    assert worksheet["P4"].value == "0019074348179017"
    assert worksheet["P4"].number_format == "@"
    assert worksheet.column_dimensions["A"].width == 22
    assert worksheet.column_dimensions["Q"].width == 46
    assert worksheet.row_dimensions[4].height == 21
    workbook.close()
