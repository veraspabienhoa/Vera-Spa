from __future__ import annotations

from datetime import date

import vera_web_v2_payroll as payroll


class _ScalarRows:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _statement):
        return _ScalarRows(self._rows)


def test_latest_saved_draft_skips_invalid_newer_entry(monkeypatch):
    rows = [
        {"start": "không hợp lệ", "end": "2026-08-31"},
        {"start": "2026-08-16", "end": "2026-08-31"},
        {"start": "2026-08-01", "end": "2026-08-15"},
    ]
    requested = []

    def fake_saved_draft(_conn, start, end, _norm):
        requested.append((start, end))
        return {
            "period_label": "Kỳ 2 - Tháng 8/2026",
            "start": start.isoformat(),
            "end": end.isoformat(),
            "rows": [{"Tên Hệ thống": "Mỹ Duyên"}],
        }

    monkeypatch.setattr(payroll, "_saved_draft", fake_saved_draft)

    draft = payroll._latest_saved_draft(_Connection(rows), lambda value: str(value).casefold())

    assert requested == [(date(2026, 8, 16), date(2026, 8, 31))]
    assert draft["period_label"] == "Kỳ 2 - Tháng 8/2026"
