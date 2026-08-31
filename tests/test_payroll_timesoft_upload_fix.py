from __future__ import annotations

from datetime import date
from io import BytesIO
import re
from zipfile import ZIP_DEFLATED, ZipFile

from openpyxl import Workbook

import vera_web_v2_payroll as payroll
from vera_web_v2_payroll_timesoft_upload_fix import (
    RELEASE,
    install_payroll_timesoft_upload_fix,
)


HEADERS = list(payroll.TIMESOFT_PAYROLL_HEADERS)


def _normalise(value) -> str:
    return str(value or "").strip().casefold()


def _timesoft_workbook_with_stale_dimension() -> bytes:
    workbook = Workbook()
    worksheet = workbook.active
    worksheet.title = "Báo cáo doanh thu hóa đơn"
    worksheet.append([""] * 11)
    worksheet.append([""] * 11)
    worksheet.append(HEADERS)
    worksheet.append([1, "31/08/2026 23:52", "HDS1", "", "", "90'", 350000, 0, "Quỳnh Phương", "", ""])
    worksheet.append([2, "31/08/2026 23:52", "HDS1", "", "", "Tip_250", 250000, 0, "Quỳnh Phương", "", ""])
    worksheet.append([3, "31/08/2026 23:32", "HDS2", "", "", "Tip-300", 300000, 0, "Mỹ Duyên", "", ""])
    worksheet.append([4, "31/08/2026 23:11", "HDS3", "", "", "TIP 200", 200000, 0, "Bảo Ngọc", "", ""])

    original = BytesIO()
    workbook.save(original)
    workbook.close()

    source = BytesIO(original.getvalue())
    output = BytesIO()
    with ZipFile(source, "r") as zin, ZipFile(output, "w", ZIP_DEFLATED) as zout:
        for info in zin.infolist():
            payload = zin.read(info.filename)
            if info.filename == "xl/worksheets/sheet1.xml":
                text = payload.decode("utf-8")
                text, replacements = re.subn(
                    r'<dimension ref="[^"]+"\s*/>',
                    '<dimension ref="A1:K4"/>',
                    text,
                    count=1,
                )
                assert replacements == 1
                payload = text.encode("utf-8")
            zout.writestr(info, payload)
    return output.getvalue()


def test_payroll_reader_ignores_stale_timesoft_dimension_and_finds_tip_rows():
    install_payroll_timesoft_upload_fix()
    assert getattr(payroll, "_timesoft_upload_dimension_fix_release") == RELEASE

    source = payroll._read_source(_timesoft_workbook_with_stale_dimension())
    assert len(source) == 4
    assert source["item"].tolist() == ["90'", "Tip_250", "Tip-300", "TIP 200"]

    tips, summary = payroll._tip_rows(
        source,
        date(2026, 8, 16),
        date(2026, 8, 31),
        _normalise,
    )
    assert len(tips) == 3
    assert summary["tip_rows"] == 3
    assert summary["salary_total"] == 750000
