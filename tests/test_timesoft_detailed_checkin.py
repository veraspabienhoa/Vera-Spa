from datetime import date
from io import BytesIO
from types import SimpleNamespace

import pandas as pd
from openpyxl import Workbook

import timesoft_detailed_checkin as detail


def _workbook_bytes() -> bytes:
    wb = Workbook()
    summary = wb.active
    summary.title = "bc checkin"
    summary.append(["STT", "Ngày", "Tên nhân viên", "Thời gian checkin", "Thời gian checkout"])
    summary.append([1, "01/09/2026", "Tiên Tiên", "01/09/2026 09:57:17", "01/09/2026 17:20:07"])

    raw = wb.create_sheet("lich-su-checkin")
    raw.append(["STT", "Mã nhân viên", "Tên nhân viên", "Số điện thoại", "Mã chấm công", "Thời gian"])
    for index, clock in enumerate(
        ["17:20:07", "17:19:58", "15:16:16", "09:57:19", "09:57:17"],
        start=1,
    ):
        raw.append([
            index,
            "EMP0000282",
            "Tiên Tiên",
            "0878467424",
            1681,
            f"01/09/2026 {clock}",
        ])

    stream = BytesIO()
    wb.save(stream)
    wb.close()
    return stream.getvalue()


def test_parse_workbook_prefers_raw_history_sheet():
    df = detail._parse_workbook(_workbook_bytes(), date(2026, 9, 1))

    assert len(df) == 5
    assert set(df["EmployeeName"]) == {"Tiên Tiên"}
    assert df["MachineTimeStr"].tolist() == [
        "01/09/2026 17:20:07",
        "01/09/2026 17:19:58",
        "01/09/2026 15:16:16",
        "01/09/2026 09:57:19",
        "01/09/2026 09:57:17",
    ]


def test_install_combines_summary_and_raw_faceid_rows():
    content = _workbook_bytes()

    class Response:
        status_code = 200
        url = "https://vera.timesoft.vn/Report/ReportEmployeeCheckin/ExportCheckinLogElastic"

        def __init__(self):
            self.content = content

        def raise_for_status(self):
            return None

    class Session:
        def get(self, *args, **kwargs):
            return Response()

    summary_df = pd.DataFrame([
        {
            "EmployeeName": "Tiên Tiên",
            "MachineTimeCheckInStr": "01/09/2026 09:57:17",
        }
    ])
    ts = SimpleNamespace(
        BASE_URL="https://vera.timesoft.vn",
        REPORT_CHECKIN_PAGE="/Report/ReportEmployeeCheckin/Index",
        _date_range_text=lambda start, end: f"{start:%d/%m/%Y} - {end:%d/%m/%Y}",
        fetch_checkin=lambda session, target_date: (summary_df.copy(), {"Total": 1}),
    )

    detail.install(ts)
    combined, meta = ts.fetch_checkin(Session(), date(2026, 9, 1))

    assert len(combined) == 6
    assert meta["SummaryRows"] == 1
    assert meta["RawLogRows"] == 5
    assert meta["CombinedRows"] == 6
    assert meta["DetailedLogReady"] is True


def test_install_keeps_summary_when_detail_export_fails():
    class Session:
        def get(self, *args, **kwargs):
            raise RuntimeError("detail endpoint unavailable")

    summary_df = pd.DataFrame([
        {
            "EmployeeName": "Tiên Tiên",
            "WorkDateStr": "01/09/2026",
            "MachineTimeCheckInStr": "01/09/2026 09:57:17",
            "MachineTimeCheckOutStr": "01/09/2026 17:20:07",
        }
    ])
    logs = []
    ts = SimpleNamespace(
        BASE_URL="https://vera.timesoft.vn",
        REPORT_CHECKIN_PAGE="/Report/ReportEmployeeCheckin/Index",
        _date_range_text=lambda start, end: f"{start:%d/%m/%Y} - {end:%d/%m/%Y}",
        fetch_checkin=lambda session, target_date: (summary_df.copy(), {"Total": 1}),
        _log=logs.append,
    )

    detail.install(ts)
    combined, meta = ts.fetch_checkin(Session(), date(2026, 9, 1))

    assert len(combined) == 1
    assert combined.iloc[0]["MachineTimeCheckInStr"] == "01/09/2026 09:57:17"
    assert meta["SummaryRows"] == 1
    assert meta["RawLogRows"] == 0
    assert meta["CombinedRows"] == 1
    assert meta["DetailedLogReady"] is False
    assert "detail endpoint unavailable" in meta["DetailedLogError"]
    assert any("TIMESOFT DETAIL FALLBACK" in line for line in logs)
