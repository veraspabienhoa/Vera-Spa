from datetime import date

from vera_web_v2_purchase_reconcile_v2 import (
    _enhanced_comparison,
    _status_for_difference,
)


def test_reconcile_status_thresholds():
    assert _status_for_difference(0) == "KHỚP"
    assert _status_for_difference(2_000) == "GẦN KHỚP"
    assert _status_for_difference(-5_000) == "GẦN KHỚP"
    assert _status_for_difference(5_001) == "KHÔNG KHỚP"
    assert _status_for_difference(-9_000) == "KHÔNG KHỚP"


def test_enhanced_comparison_includes_detail_and_near_match():
    purchase_rows = [
        {"date": date(2026, 8, 27), "amount": 4_135_000, "item": "Nước lau sàn", "buyer": "Đạt"},
    ]
    ledger_rows = [
        {"date": date(2026, 8, 27), "amount": 4_133_000, "is_purchase": True, "note": "Mua đồ ngày 27/08/2026"},
    ]
    rows = _enhanced_comparison(purchase_rows, ledger_rows)
    assert len(rows) == 1
    row = rows[0]
    assert row["difference"] == 2_000
    assert row["status"] == "GẦN KHỚP"
    assert row["matched"] is True
    assert "Nước lau sàn" in row["purchase_detail_text"]
    assert "Mua đồ ngày 27/08/2026" in row["ledger_detail_text"]


def test_enhanced_comparison_marks_over_5000_as_mismatch():
    purchase_rows = [{"date": date(2026, 8, 28), "amount": 2_725_000, "item": "Tổng mua", "buyer": ""}]
    ledger_rows = []
    row = _enhanced_comparison(purchase_rows, ledger_rows)[0]
    assert row["status"] == "KHÔNG KHỚP"
    assert row["matched"] is False
