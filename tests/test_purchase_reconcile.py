from datetime import date

import vera_web_v2_purchase_reconcile as reconcile
from vera_web_v2_purchase_reconcile import _comparison, _parse_revenue_input, _resolve_range


def _norm(value):
    return str(value or "").strip().lower().replace("đ", "d")


def test_date_presets():
    today = date(2026, 8, 31)
    assert _resolve_range("today", None, None, today=today) == (date(2026, 8, 31), date(2026, 8, 31))
    assert _resolve_range("yesterday", None, None, today=today) == (date(2026, 8, 30), date(2026, 8, 30))
    assert _resolve_range("this_week", None, None, today=today) == (date(2026, 8, 31), date(2026, 9, 6))
    assert _resolve_range("last_week", None, None, today=today) == (date(2026, 8, 24), date(2026, 8, 30))
    assert _resolve_range("this_month", None, None, today=today) == (date(2026, 8, 1), date(2026, 8, 31))
    assert _resolve_range("last_month", None, None, today=today) == (date(2026, 7, 1), date(2026, 7, 31))


def test_note_date_wins_over_wrong_transaction_date_for_purchase_rows():
    values = [
        ["Dấu thời gian", "Loại giao dịch", "Số tiền", "Ngày giao dịch", "Ghi chú", "Địa chỉ email"],
        ["29/08/2026 09:40", "Chi", "4,133,000", "29/08/2026", "Mua đồ ngày 27/08/2026", "x@example.com"],
    ]
    rows = _parse_revenue_input(values, _norm)
    assert len(rows) == 1
    assert rows[0]["date"] == date(2026, 8, 27)
    assert rows[0]["is_purchase"] is True
    assert rows[0]["amount"] == 4_133_000


def test_daily_comparison_detects_two_thousand_difference():
    purchase_rows = [{"date": date(2026, 8, 27), "amount": 4_135_000}]
    ledger_rows = [{"date": date(2026, 8, 27), "amount": 4_133_000, "is_purchase": True}]
    rows = _comparison(purchase_rows, ledger_rows)
    assert rows == [{
        "date": "2026-08-27",
        "date_label": "27/08/2026",
        "purchase_total": 4_135_000.0,
        "ledger_purchase_total": 4_133_000.0,
        "difference": 2_000.0,
        "matched": False,
    }]


def test_purchase_report_falls_back_to_public_drive_without_credentials(monkeypatch):
    expected = b"PK\x03\x04xlsb-content"

    monkeypatch.setattr(
        reconcile,
        "google_credentials",
        lambda _scopes: (_ for _ in ()).throw(RuntimeError("no application default credentials")),
    )
    monkeypatch.setattr(
        reconcile,
        "_public_drive_download",
        lambda file_id: expected if file_id == reconcile.PURCHASE_REPORT_FILE_ID else b"",
    )

    assert reconcile._drive_download_purchase_report() == expected


def test_public_drive_download_rejects_login_or_preview_html(monkeypatch):
    class Response:
        content = b"<html>Google Drive login</html>"

        def raise_for_status(self):
            return None

    monkeypatch.setattr(reconcile.requests, "get", lambda *_args, **_kwargs: Response())

    try:
        reconcile._public_drive_download("file-id")
    except RuntimeError as exc:
        assert "not an XLSB" in str(exc)
    else:
        raise AssertionError("HTML response must not be accepted as XLSB")
