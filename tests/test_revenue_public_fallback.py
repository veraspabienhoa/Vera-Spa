from datetime import date

import vera_web_v2_revenue_leave_list as revenue


class _Response:
    text = '"Dấu thời gian","Loại giao dịch","Số tiền"\n"01/09/2026","Thu","1.000 đ"\n'
    encoding = None

    def raise_for_status(self):
        return None


def test_revenue_reader_falls_back_to_public_csv_without_google_credentials(monkeypatch):
    class BrokenClient:
        def open_by_key(self, _key):
            raise RuntimeError("no application default credentials")

    captured = {}

    def fake_get(url, *, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return _Response()

    monkeypatch.setattr(revenue.requests, "get", fake_get)

    values = revenue._read_revenue_values(lambda: BrokenClient())

    assert values[0][1:] == ["Loại giao dịch", "Số tiền"]
    assert values[1][1:] == ["Thu", "1.000 đ"]
    assert captured["url"].endswith("/export")
    assert captured["params"] == {"format": "csv", "gid": revenue.REVENUE_INPUT_GID}
    assert captured["timeout"] == 30


def test_revenue_reader_keeps_authenticated_google_sheets_as_primary(monkeypatch):
    expected = [["Loại giao dịch", "Số tiền"], ["Chi", "250.000 đ"]]

    class Worksheet:
        def get_all_values(self):
            return expected

    class Workbook:
        def worksheet(self, name):
            assert name == "Input"
            return Worksheet()

    class Client:
        def open_by_key(self, key):
            assert key == revenue.REVENUE_SPREADSHEET_ID
            return Workbook()

    monkeypatch.setattr(
        revenue.requests,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("public fallback should not run")),
    )

    assert revenue._read_revenue_values(lambda: Client()) == expected


def test_report_totals_use_b2_for_income_and_b3_for_expense():
    result = revenue._report_totals([
        ["20.856.783.533 đ"],
        ["19.958.603.325 đ"],
    ])

    assert result == {
        "total_income": 20_856_783_533,
        "total_expense": 19_958_603_325,
    }


def test_report_reader_uses_authenticated_report_cells_first(monkeypatch):
    expected = [["20.856.783.533 đ"], ["19.958.603.325 đ"]]

    class Worksheet:
        def get(self, range_name):
            assert range_name == "B2:B3"
            return expected

    class Workbook:
        def worksheet(self, name):
            assert name == "Report"
            return Worksheet()

    class Client:
        def open_by_key(self, key):
            assert key == revenue.REVENUE_SPREADSHEET_ID
            return Workbook()

    monkeypatch.setattr(
        revenue.requests,
        "get",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(AssertionError("public fallback should not run")),
    )

    assert revenue._read_revenue_report_values(lambda: Client()) == expected


def test_report_reader_falls_back_to_public_report_range(monkeypatch):
    class BrokenClient:
        def open_by_key(self, _key):
            raise RuntimeError("no application default credentials")

    class ReportResponse:
        text = '"20.856.783.533 đ"\n"19.958.603.325 đ"\n'
        encoding = None

        def raise_for_status(self):
            return None

    captured = {}

    def fake_get(url, *, params, timeout):
        captured.update(url=url, params=params, timeout=timeout)
        return ReportResponse()

    monkeypatch.setattr(revenue.requests, "get", fake_get)

    values = revenue._read_revenue_report_values(lambda: BrokenClient())

    assert revenue._report_totals(values)["total_income"] == 20_856_783_533
    assert revenue._report_totals(values)["total_expense"] == 19_958_603_325
    assert captured["url"].endswith("/gviz/tq")
    assert captured["params"] == {
        "tqx": "out:csv",
        "sheet": "Report",
        "range": "B2:B3",
        "headers": "0",
    }
    assert captured["timeout"] == 30


def test_summary_uses_every_full_input_row_from_visible_period_start():
    values = [
        ["Dấu thời gian", "Loại giao dịch", "Số tiền", "Ngày giao dịch", "Ghi chú"],
        ["", "Chi", "20", "02/07/2026", "Chi phí nhập trước dòng bắt đầu hiển thị"],
        ["", "Thu", "999", "30/06/2026", "Ngoài kỳ"],
        ["", "Thu", "100", "01/07/2026", "Doanh thu ngày 01/07/2026"],
        ["", "Chi", "30", "03/07/2026", "Mua đồ ngày 03/07/2026"],
    ]

    result = revenue._revenue_summary(values, lambda value: str(value or "").strip().lower(), period_start=date(2026, 7, 1))

    assert result["start_date"] == "2026-07-01"
    assert result["transaction_count"] == 3
    assert result["total_income"] == 100
    assert result["total_expense"] == 50


def test_revenue_period_always_starts_on_5_september_2025():
    full = [
        ["Loại giao dịch", "Số tiền", "Ngày giao dịch"],
        ["Thu", "999", "01/01/2026"],
        ["Thu", "100", "01/07/2026"],
        ["Chi", "20", "02/07/2026"],
    ]
    norm = lambda value: str(value or "").strip().lower()

    assert revenue._revenue_period_start(norm, full) == date(2025, 9, 5)
