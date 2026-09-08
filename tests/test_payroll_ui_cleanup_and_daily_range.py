from datetime import date
from pathlib import Path

from vera_web_v2_department_payroll import _accumulated_month_range


ROOT = Path(__file__).resolve().parents[1]


def test_current_department_payroll_accumulates_through_yesterday():
    start, end, label = _accumulated_month_range("2026-09", today=date(2026, 9, 8))
    assert start == date(2026, 9, 1)
    assert end == date(2026, 9, 7)
    assert label == "09/2026"


def test_completed_month_keeps_its_full_range():
    start, end, _ = _accumulated_month_range("2026-08", today=date(2026, 9, 8))
    assert start == date(2026, 8, 1)
    assert end == date(2026, 8, 31)


def test_ktv_payroll_removes_history_and_obligation_sections():
    source = (ROOT / "web-v2/src/pages/PayrollPageEnhanced.jsx").read_text(encoding="utf-8")
    for text in ("LỊCH SỬ BẢNG LƯƠNG", "NGHĨA VỤ VI PHẠM", "🔴 Nợ do Thực nhận âm"):
        assert text not in source


def test_completed_accumulation_table_displays_refund_note():
    backend = (ROOT / "vera_web_v2_payroll_personal.py").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/PayrollPersonalTracking.jsx").read_text(encoding="utf-8")
    assert '"refund_note": " · ".join(refund_notes)' in backend
    assert "Ghi chú hoàn trả" in page
    assert "showRefundNote" in page
