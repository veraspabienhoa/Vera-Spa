from datetime import date
from pathlib import Path

import vera_auto_check as auto_check


class _Rows:
    def __init__(self, rows):
        self._rows = rows

    def mappings(self):
        return self

    def all(self):
        return self._rows


class _Connection:
    def __init__(self, rows):
        self._rows = rows

    def execute(self, _query, _params):
        return _Rows(self._rows)


def test_registered_late_uses_1700_and_ignores_automatic_penalties():
    conn = _Connection([
        {
            "employee_name": "Thúy Vy",
            "leave_reason": "Đi trễ CÓ phép",
            "source_sheet_id": "postgres:web_v2",
            "updated_by": "Thúy Vy",
        },
        {
            "employee_name": "Thúy Vy",
            "leave_reason": "Đi trễ không phép",
            "source_sheet_id": "postgres:auto_check",
            "updated_by": "ĐỒNG BỘ TIMESOFT - PHẠT TRỰC TIẾP",
        },
        {
            "employee_name": "Thúy Vy",
            "leave_reason": "Đi trễ không phép",
            "source_sheet_id": "legacy-sheet",
            "updated_by": "AUTO UPDATE 24/7 - TIMESOFT",
        },
    ])

    reasons, baseline, matched = auto_check.registered_late_for_day(
        conn, date(2026, 9, 2), "Thuy Vy",
    )

    assert reasons == ["Đi trễ CÓ phép"]
    assert baseline == 17 * 60
    assert matched == "Đi trễ CÓ phép"


def test_frequent_sync_is_authoritative_for_timesoft_late_penalties():
    root = Path(__file__).resolve().parents[1]
    snapshot = (root / "timesoft_snapshot_job.py").read_text(encoding="utf-8")
    sync = (root / "timesoft_sync_job.py").read_text(encoding="utf-8")
    legacy = (root / "auto_penalty_runtime_wrapper_v39.py").read_text(encoding="utf-8")

    assert "_snapshot_only_auto_config" not in snapshot
    assert "ts.process_tour_penalties = _skip_tour_penalties" in snapshot
    assert "ĐỒNG BỘ TIMESOFT - PHẠT TRỰC TIẾP" in sync
    assert "auto_check.registered_late_for_day" in sync
    assert "delegated_to_postgres_sync" in legacy
    assert "return _ORIGINAL_PROCESS_TIMESOFT" not in legacy
