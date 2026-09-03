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
    assert captured["params"] == {"tqx": "out:csv", "sheet": "Input"}
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
