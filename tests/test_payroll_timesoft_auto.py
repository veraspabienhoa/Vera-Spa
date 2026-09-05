from __future__ import annotations

from datetime import date
import unicodedata

import timesoft_sync_job as sync_job
import vera_web_v2_payroll_timesoft_auto as payroll_auto


def _norm(value) -> str:
    raw = unicodedata.normalize("NFD", str(value or ""))
    return " ".join(
        "".join(character for character in raw if unicodedata.category(character) != "Mn")
        .replace("đ", "d").replace("Đ", "D").casefold().split()
    )


def test_timesoft_summary_selects_product_service_response(monkeypatch):
    calls = []

    def fake_post(_session, _api, _referer, payload):
        type_data = payload["objectSearch"]["TypeData"]
        calls.append(type_data)
        if type_data == 1:
            return {"Data": [{"DateGroupStr": "05/09/2026", "TotalMoney": 10_000_000}], "Total": 1}
        return {
            "Data": [
                {"DateGroupStr": "05/09/2026", "ProductName": "Tip_250", "TotalMoney": 250_000, "SellerName": "Linh Đan"},
                {"DateGroupStr": "05/09/2026", "ProductName": "90'", "TotalMoney": 400_000, "SellerName": "Linh Đan"},
            ],
            "Total": 2,
        }

    monkeypatch.setattr(sync_job, "post_json", fake_post)

    frame, meta = sync_job.fetch_summary(object(), date(2026, 9, 5))

    assert calls == [1, 2]
    assert list(frame["ProductName"]) == ["Tip_250", "90'"]
    assert meta["PayrollTypeData"] == 2
    assert meta["PayrollMappingMode"] == "product_detail"
    assert meta["PayrollTipRows"] == 1
    assert sync_job._payroll_invoice_snapshot_valid(
        frame.to_dict(orient="records"),
        f"2026-09-05|{sync_job.PAYROLL_SUMMARY_DETAIL_RELEASE}|product_detail",
    )
    assert not sync_job._payroll_invoice_snapshot_valid(
        [{"DateGroupStr": "05/09/2026", "TotalMoney": 10_000_000}],
        "2026-09-05",
    )


class _Result:
    def __init__(self, rows):
        self.rows = rows

    def mappings(self):
        return self

    def all(self):
        return self.rows

    def first(self):
        return self.rows[0] if self.rows else None


class _Connection:
    def execute(self, statement, params=None):
        sql = str(statement)
        if "FROM employees" in sql:
            return _Result([{"username": "Linh Đan", "full_name": "Linh Đan"}])
        assert params == {"key": "timesoft_summary_invoice_20260905"}
        return _Result([{
            "payload": [{
                "DateGroupStr": "05/09/2026",
                "ProductName": "Tip_250",
                "TotalMoney": 250_000,
                "SellerName": "Linh Đan",
            }],
            "row_count": 1,
        }])


def test_payroll_auto_maps_timesoft_product_fields_to_canonical_tip():
    rows, summary = payroll_auto._canonical_tip_rows(
        _Connection(),
        date(2026, 9, 5),
        date(2026, 9, 5),
        _norm,
    )

    assert rows == [{
        "time": "05/09/2026",
        "item": "Tip_250",
        "amount": 250_000,
        "employee": "Linh Đan",
    }]
    assert summary["tip_rows"] == 1

