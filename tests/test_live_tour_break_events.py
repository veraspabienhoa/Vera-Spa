from datetime import datetime, timedelta

import pytest
from fastapi import HTTPException

import vera_web_v2_live_tour as live


START = datetime(2026, 9, 5, 13, 0, tzinfo=live.VN_TZ)


def employee():
    return {
        "id": "e1", "name": "Nguyễn An", "stt": 1, "work_status": "Đi làm",
        "shift": "Ca 1", "status": "", "service": "", "room": "",
        "break_started_at": "", "sort_index": 0, "hidden": False,
    }


def test_break_ledger_appends_start_and_end_with_ninety_minute_outcome_and_clocks():
    state = live._empty_state(START)
    state["employees"] = [employee()]

    started = live._apply_action(state, "start_break", {"employee_id": "e1"}, "manager", START)
    ended = live._apply_action(
        state, "end_break", {"employee_id": "e1"}, "manager", START + timedelta(minutes=95),
    )

    assert len(state["break_events"]) == 2
    start_event, end_event = state["break_events"]
    assert started["break_event"] == start_event
    assert ended["break_event"] == end_event
    assert start_event["event_type"] == "start"
    assert start_event["allowance_minutes"] == 90
    assert end_event["event_type"] == "end"
    assert end_event["start_event_id"] == start_event["id"]
    assert end_event["minutes"] == 95
    assert end_event["remaining_minutes"] == 0
    assert end_event["late_minutes"] == 5
    assert end_event["outcome"] == "Quá 90 phút"
    assert end_event["actor"] == "manager"
    assert state["employees"][0]["clock_out"] == START.isoformat()
    assert state["employees"][0]["clock_in"] == (START + timedelta(minutes=95)).isoformat()


def test_break_invalid_transition_does_not_append_event():
    state = live._empty_state(START)
    state["employees"] = [employee()]
    with pytest.raises(HTTPException) as error:
        live._apply_action(state, "end_break", {"employee_id": "e1"}, "manager", START)
    assert error.value.status_code == 409
    assert state["break_events"] == []


def test_restore_preserves_append_only_break_ledger():
    state = live._empty_state(START)
    state["employees"] = [employee()]
    live._apply_action(state, "start_break", {"employee_id": "e1"}, "manager", START)
    live._apply_action(state, "end_break", {"employee_id": "e1"}, "manager", START + timedelta(minutes=30))
    backup = live._apply_action(state, "backup", {"name": "before"}, "manager", START)
    state["break_events"].append({"id": "later", "event_type": "start", "at": START.isoformat()})

    live._apply_action(
        state, "restore", {"backup_id": backup["backup"]["id"]}, "manager", START,
    )

    assert [item["id"] for item in state["break_events"]][-1] == "later"
    assert len(state["break_events"]) == 3


def test_break_ledger_is_admin_only_in_state_response_and_exportable():
    state = live._empty_state(START)
    state["employees"] = [employee()]
    live._apply_action(state, "start_break", {"employee_id": "e1"}, "manager", START)

    view = live._state_response(state, 1, START, can_operate=True)
    admin = live._state_response(state, 1, START, can_admin=True)
    title, headers, rows = live._export_rows(state, "breaks", START)

    assert view["break_events"] == []
    assert view["state"]["break_events"] == []
    assert admin["break_events"][0]["employee_id"] == "e1"
    assert title == "Nghi_giua_ca"
    assert "Định mức" in headers
    assert rows[0][headers.index("Người thao tác")] == "manager"


def test_break_remaining_column_is_derived_from_active_clock():
    state = live._empty_state(START)
    worker = employee()
    worker["break_started_at"] = START.isoformat()
    state["employees"] = [worker]

    record = live._employee_record(worker, START + timedelta(minutes=37, seconds=40))

    assert "TG nghỉ còn lại" in live.BOARD_COLUMNS
    assert record["TG nghỉ còn lại"] == 53
