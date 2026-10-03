from datetime import date
from io import BytesIO

from openpyxl import load_workbook

from vera_web_v2_excel_export_style import style_workbook_bytes
from vera_web_v2_payroll import _new_payroll_workbook, _read_draft_workbook


FIELDS = [
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
        "TT": 1,
        "Tên Hệ thống": "An An",
        "Họ và tên": "Đinh Thúy An",
        "Tiền Lương": 28_800_000,
        "Tiền Hỗ Trợ Hoàn Lại": 0,
        "Hoàn trả tiền tích lũy": 0,
        "Tích lũy": 0,
        "Chi Phí Sinh Hoạt": 150_000,
        "Tiền phạt trong tháng": 500_000,
        "Vi phạm kỳ trước": 0,
        "Tiền ứng lương": 0,
        "Tiền hỗ trợ Locker": 80_000,
        "Số tiền thực nhận": 28_070_000,
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
    assert str(worksheet.merged_cells) == "B2:C2"
    assert worksheet.max_column == 15
    assert worksheet["A1"].value == "BẢNG LƯƠNG NHÂN VIÊN"
    assert worksheet["A2"].value == "KỲ LƯƠNG"
    assert worksheet["B2"].value == "Từ ngày 01-09-2026 đến 15-09-2026"
    assert [worksheet.cell(3, column).value for column in range(1, 16)] == FIELDS
    assert worksheet["A4"].value == 1
    assert worksheet["B4"].value == "An An"
    assert worksheet.freeze_panes == "A4"
    assert worksheet.auto_filter.ref == "A3:O4"

    for coordinate in ("A1", "O1", "A2", "B2", "O2", "A3", "O3"):
        cell = worksheet[coordinate]
        assert cell.fill.fgColor.rgb[-6:] == "1F513F"
        assert cell.font.bold is True
        assert cell.font.color.rgb[-6:] == "FFFFFF"

    assert worksheet["D4"].number_format == "#,##0"
    assert worksheet["M4"].number_format == "#,##0"
    assert worksheet["N4"].value == "0019074348179017"
    assert worksheet["N4"].number_format == "@"
    assert worksheet.column_dimensions["A"].width == 10.14
    assert worksheet.column_dimensions["O"].width == 46
    for letter in "DEFGHIJKLM":
        assert worksheet.column_dimensions[letter].width == 11.14
    assert worksheet["B2"].alignment.horizontal == "center"
    for letter in "DEFGHIJKL":
        assert worksheet[f"{letter}5"].value == f"=SUM({letter}4:{letter}4)"
    assert worksheet.row_dimensions[4].height == 21
    workbook.close()


def test_a4_landscape_print_settings_and_positive_net_total_survive_styling():
    records = [{'TT': index, 'Tên Hệ thống': f'Staff {index}', 'Số tiền thực nhận': amount}
               for index, amount in enumerate([2_000_000, -450_000, 0, 1_480_000], 1)]
    raw = _new_payroll_workbook(records, FIELDS, date(2026, 9, 16), date(2026, 9, 30))
    workbook = load_workbook(BytesIO(style_workbook_bytes(raw)))
    ws = workbook.active
    assert ws['A8'].value == 'Tổng số tiền'
    assert ws['M8'].value == '=SUMIF(M4:M7,">=0",M4:M7)'
    assert sum(max(0, ws.cell(row, 13).value) for row in range(4, 8)) == 3_480_000
    assert ws.auto_filter.ref == 'A3:O7'
    assert ws.page_setup.orientation == 'landscape'
    assert ws.page_setup.paperSize == int(ws.PAPERSIZE_A4)
    assert ws.page_setup.fitToWidth == ws.page_setup.fitToHeight == 1
    assert ws.sheet_properties.pageSetUpPr.fitToPage
    assert ws.page_margins.left == ws.page_margins.right == 0.25
    assert ws.page_margins.top == ws.page_margins.bottom == 0.75
    assert str(ws.print_area).endswith('$A$1:$O$8')
    workbook.close()


def test_export_with_totals_and_merged_period_can_be_imported_again():
    start, end = date(2026, 9, 16), date(2026, 9, 30)
    records = [{"TT": 1, "Tên Hệ thống": "Staff A", "Tiền Lương": 1000000,
                "Số tiền thực nhận": 900000}]
    raw = style_workbook_bytes(_new_payroll_workbook(records, FIELDS, start, end))
    rows, labels, ranges = _read_draft_workbook(raw)
    assert len(rows) == 1
    assert rows[0]["Tên Hệ thống"] == "Staff A"
    assert rows[0]["Số tiền thực nhận"] == 900000
    assert ranges == {(start, end)}
