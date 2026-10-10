"""Read-only HTTP regressions for the training roster, report and full exports.

SQLite executes the real read SQL against synthetic rows; only schema migration
and the unrelated HR registry are replaced. No production account is used.
"""
from copy import deepcopy
from datetime import date
from decimal import Decimal
import json

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from pydantic import BaseModel
import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.pool import StaticPool

import vera_web_v2_training as training
import vera_web_v2_hr as hr


class Identity(BaseModel):
    employee_username: str = "admin"
    role: str = "admin"


TABLES = {
    "employees": "username TEXT, full_name TEXT, role TEXT, payload TEXT",
    "vera_training_session": "id TEXT, employee_username TEXT, trainer_username TEXT, training_date DATE, start_time TEXT, end_time TEXT, topic TEXT, learning_attitude TEXT, skill_grade TEXT, strengths TEXT, improvements TEXT, notes TEXT, status TEXT, created_at TEXT",
    "vera_evaluation_cycle": "id TEXT, name TEXT, start_date DATE, end_date DATE",
    "vera_evaluation_assignment": "id TEXT, cycle_id TEXT, employee_username TEXT, evaluator_username TEXT, status TEXT",
    "vera_employee_evaluation": "assignment_id TEXT, craft_score INTEGER, communication_score INTEGER, attitude_score INTEGER, discipline_score INTEGER, appearance_score INTEGER, hygiene_score INTEGER, attendance_score INTEGER, strengths TEXT, improvements TEXT, comments TEXT, submitted_at TEXT",
}
SCORE_KEYS = ("craft_score", "communication_score", "attitude_score", "discipline_score", "appearance_score", "hygiene_score", "attendance_score")


def insert(conn, table, **row):
    conn.execute(text(f"INSERT INTO {table} ({','.join(row)}) VALUES ({','.join(':'+key for key in row)})"), row)


def session(conn, id, day, *, employee="alice", trainer="leader", grade="A", **extra):
    insert(conn, "vera_training_session", **{
        "id": id, "employee_username": employee, "trainer_username": trainer,
        "training_date": day, "start_time": "09:00:00", "end_time": "10:00:00", "topic": id,
        "learning_attitude": "Tốt", "skill_grade": grade, "strengths": "Điểm mạnh",
        "improvements": "Cần cải thiện", "notes": "Ghi chú", "status": "submitted",
        # Training date is authoritative even across Vietnam/UTC midnight.
        "created_at": "2026-09-30T17:05:00+00:00", **extra,
    })


def evaluation(conn, id, cycle, day, *, employee="alice", evaluator="leader", score=5, status="submitted", **extra):
    if not conn.execute(text("SELECT 1 FROM vera_evaluation_cycle WHERE id=:id"), {"id": cycle}).first():
        insert(conn, "vera_evaluation_cycle", id=cycle, name=f"Đợt {cycle}", start_date="2026-09-01", end_date=day)
    insert(conn, "vera_evaluation_assignment", id=id, cycle_id=cycle, employee_username=employee, evaluator_username=evaluator, status=status)
    insert(conn, "vera_employee_evaluation", **{
        "assignment_id": id, **{key: score for key in SCORE_KEYS}, "strengths": "Điểm mạnh",
        "improvements": "Cần cải thiện", "comments": "Đánh giá kỹ thuật",
        # The cycle end_date, not UTC submitted_at, selects comprehensive records.
        "submitted_at": "2026-11-01T17:05:00+00:00", **extra,
    })


@pytest.fixture
def report_client(monkeypatch):
    engine = create_engine("sqlite://", poolclass=StaticPool, connect_args={"check_same_thread": False})
    with engine.begin() as conn:
        for table, columns in TABLES.items():
            conn.execute(text(f"CREATE TABLE {table} ({columns})"))
        for username, role, payload in (
            ("admin", "admin", {}), ("leader", "leader", {}), ("leader2", "leader", {}),
            ("manager", "quanly", {}), ("alice", "nhanvien", {}), ("betty", "letan", {}),
            ("empty", "nhanvien", {}), ("draft", "nhanvien", {}), ("only-evaluated", "nhanvien", {}),
            ("inactive", "nhanvien", {"employment_status": "inactive"}),
            ("deleted", "nhanvien", {"__deleted": "true"}),
        ):
            insert(conn, "employees", username=username, full_name=username, role=role, payload=json.dumps({"employment_status": "active", **payload}))
        for day, grade in (("2026-09-30", "E"), ("2026-10-01", "A"), ("2026-10-10", "B"), ("2026-10-31", "A+"), ("2026-11-01", "C")):
            session(conn, f"daily-{day}", day, grade=grade)
            evaluation(conn, f"eval-{day}", day, day, score=4 if grade == "B" else 5)
        session(conn, "betty", "2026-10-10", employee="betty", trainer="manager")
        session(conn, "inactive", "2026-10-10", employee="inactive")
        session(conn, "deleted", "2026-10-10", employee="deleted")
        evaluation(conn, "draft-only", "draft", "2026-10-10", employee="draft", status="draft")
        evaluation(conn, "evaluated-only", "only", "2026-10-10", employee="only-evaluated")
    monkeypatch.setattr(training, "_schema", lambda _conn: None)
    monkeypatch.setattr(hr, "registry", lambda _conn: {"departments": hr.DEFAULT_DEPARTMENTS, "assignments": {"alice": "leader"}})
    state = {"identity": Identity(), "features": {"training_view"}, "active": True, "sql": []}

    def current_identity():
        if not state["active"]:
            raise HTTPException(401, "Tài khoản đã bị khóa hoặc phiên đã thu hồi.")
        return state["identity"]

    def require(_conn, _ident, feature):
        if feature not in state["features"]:
            raise HTTPException(403, "Bạn không có quyền xem đào tạo.")

    @event.listens_for(engine, "before_cursor_execute")
    def sql(_conn, _cursor, statement, _parameters, _context, _many):
        state["sql"].append(statement)

    app = FastAPI()
    training.install_training_routes(app, engine_instance=lambda: engine, current_identity=current_identity,
        require_feature=require, identity_type=Identity)
    with TestClient(app) as client:
        yield client, engine, state
    engine.dispose()


def get(client, path, **params):
    response = client.get(path, params=params)
    assert response.status_code == 200, response.text
    return response.json()


@pytest.mark.parametrize("day", ["2026-09-30", "2026-10-01", "2026-10-10", "2026-10-31", "2026-11-01"])
def test_inclusive_day_filter_matches_every_report_section_and_latest_radar(report_client, day):
    client, _, _ = report_client
    data = get(client, "/v2/training/reports/ALICE", date_from=day, date_to=day)
    assert data["employee_username"] == "alice"
    assert data["employee"]["department"] == "Leader"
    assert [item["training_date"] for item in data["progress"]] == [day]
    assert [item["end_date"] for item in data["evaluations"]] == [day]
    assert [item["end_date"] for item in data["evaluation_details"]] == [day]
    assert data["latest_radar"]["end_date"] == day
    assert {item["date"] for item in data["history"]} == {day}
    assert data["history_total"] == 2


def test_month_and_empty_ranges_do_not_leak_latest_scores(report_client):
    client, _, _ = report_client
    data = get(client, "/v2/training/reports/alice", date_from="2026-10-01", date_to="2026-10-31")
    assert len(data["progress"]) == len(data["evaluations"]) == len(data["evaluation_details"]) == 3
    assert data["history_total"] == 6
    assert data["latest_radar"]["end_date"] == "2026-10-31"
    empty = get(client, "/v2/training/reports/alice", date_from="2026-10-02", date_to="2026-10-09")
    assert empty["progress"] == empty["evaluations"] == empty["evaluation_details"] == empty["history"] == []
    assert empty["latest_radar"] is None
    assert empty["history_total"] == 0


def test_roster_uses_actual_records_same_range_role_pair_and_department(report_client):
    client, _, state = report_client
    roster = get(client, "/v2/training/report-employees", date_from="2026-10-10", date_to="2026-10-10")["employees"]
    assert {person["username"] for person in roster} == {"alice", "betty", "only-evaluated"}
    assert next(person for person in roster if person["username"] == "alice")["department"] == "Leader"
    state["identity"] = Identity(employee_username="leader", role="leader")
    assert {person["username"] for person in get(client, "/v2/training/report-employees")["employees"]} == {"alice", "only-evaluated"}
    state["identity"] = Identity(employee_username="manager", role="quanly")
    assert [person["username"] for person in get(client, "/v2/training/report-employees")["employees"]] == ["betty"]
    assert get(client, "/v2/training/report-employees", date_from="2026-12-01")["employees"] == []


def test_roster_does_not_cap_records_to_recent_300(report_client):
    client, engine, _ = report_client
    with engine.begin() as conn:
        session(conn, "old-only", "2020-02-29", employee="empty")
        for index in range(305):
            session(conn, f"recent-{index}", "2026-10-10")
    roster = get(client, "/v2/training/report-employees", date_from="2020-02-29", date_to="2020-02-29")["employees"]
    assert [person["username"] for person in roster] == ["empty"]


@pytest.mark.parametrize("path", ["/v2/training/report-employees", "/v2/training/reports/alice", "/v2/training/reports/alice/export"])
@pytest.mark.parametrize("params,expected", [
    ({"date_from": "2026-10-31", "date_to": "2026-10-01"}, 400),
    ({"date_from": "2026-02-29"}, 422),
    ({"date_to": "10-10-2026"}, 422),
])
def test_invalid_ranges_fail_clearly_without_reading_records(report_client, path, params, expected):
    client, _, state = report_client
    assert client.get(path, params=params).status_code == expected
    assert state["sql"] == []


@pytest.mark.parametrize("path", ["/v2/training/report-employees", "/v2/training/reports/alice", "/v2/training/reports/alice/export?format=pdf", "/v2/training/reports/alice/export?format=png"])
def test_every_endpoint_rechecks_feature_and_revoked_identity(report_client, path):
    client, _, state = report_client
    # A previously authorized report read is not a lasting grant for exports.
    get(client, "/v2/training/reports/alice")
    state["features"].clear()
    state["sql"].clear()
    assert client.get(path).status_code == 403
    assert state["sql"] == []
    state["features"].add("training_view")
    state["active"] = False
    assert client.get(path).status_code == 401
    assert state["sql"] == []


@pytest.mark.parametrize("suffix", ["", "/export?format=pdf", "/export?format=png"])
def test_per_employee_role_pair_checked_for_direct_report_and_exports(report_client, suffix):
    client, _, state = report_client
    state["identity"] = Identity(employee_username="leader", role="leader")
    assert client.get("/v2/training/reports/betty" + suffix).status_code == 403
    assert client.get("/v2/training/reports/inactive" + suffix).status_code == 409
    assert client.get("/v2/training/reports/deleted" + suffix).status_code == 404
    assert client.get("/v2/training/reports/nonexistent" + suffix).status_code == 404
    assert not any("FROM vera_training_session" in sql or "FROM vera_evaluation_assignment" in sql for sql in state["sql"])


def test_q_rating_and_role_filters_apply_before_aggregation_and_pagination(report_client):
    client, engine, _ = report_client
    with engine.begin() as conn:
        evaluation(conn, "low-same-cycle", "2026-10-10", "2026-10-10", evaluator="leader2", score=2, comments="Only low result")
        session(conn, "admin-session", "2026-10-10", trainer="admin", grade="A+")
    common = {"date_from": "2026-10-10", "date_to": "2026-10-10"}
    data = get(client, "/v2/training/reports/alice", **common, q="Only low result", page_size=1)
    assert data["progress"] == []
    assert len(data["evaluation_details"]) == 1
    assert data["latest_radar"]["craft"] == 2
    assert data["history_total"] == 1
    excellent = get(client, "/v2/training/reports/alice", **common, rating="excellent")
    assert len(excellent["progress"]) == 1
    assert excellent["evaluation_details"] == []
    assert excellent["latest_radar"] is None
    leader = get(client, "/v2/training/reports/alice", **common, evaluator_role="leader", page_size=1)
    assert len(leader["progress"]) == 1
    assert len(leader["evaluation_details"]) == 2
    assert leader["latest_radar"]["craft"] == 3
    assert len(leader["history"]) == 1
    assert leader["history_total"] == 3


@pytest.mark.parametrize("format,media", [("pdf", "application/pdf"), ("png", "image/png")])
def test_full_export_uses_identical_unpaginated_dto_no_mutation_and_no_db_lock(report_client, monkeypatch, format, media):
    import vera_web_v2_training_report_export as exporter
    client, engine, state = report_client
    with engine.begin() as conn:
        for index in range(151):
            session(conn, f"all-{index:03d}", "2026-10-10", notes="Xuất đầy đủ")
    expected = get(client, "/v2/training/reports/alice", date_from="2026-10-10", date_to="2026-10-10", page_size=100)
    captured = []

    def render(report, selected_format):
        assert selected_format == format
        captured.append(deepcopy(report))
        for key in ("employee_username", "progress", "evaluations", "evaluation_details", "latest_radar", "history_total"):
            # DB DATE values here are strings with SQLite and native dates on PG.
            assert report[key] == expected[key]
        assert not engine.pool.connection.in_use  # renderer runs after transaction/checkin
        return b"full-rendered-document"

    monkeypatch.setattr(exporter, "render_training_report", render)
    state["sql"].clear()
    response = client.get("/v2/training/reports/alice/export", params={"format": format, "date_from": "2026-10-10", "date_to": "2026-10-10"})
    assert response.status_code == 200, response.text
    assert response.content == b"full-rendered-document"
    assert response.headers["content-type"] == media
    assert response.headers["cache-control"] == "no-store"
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert len(expected["history"]) == 100
    assert len(captured[0]["history"]) == captured[0]["history_total"] == 153
    assert any(item["id"] == "all-150" for item in captured[0]["history"])
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in state["sql"])


def test_export_errors_are_actionable_and_do_not_return_partial_image(report_client, monkeypatch):
    import vera_web_v2_training_report_export as exporter
    client, _, _ = report_client
    for error, expected in [(exporter.ReportExportTooLarge("Báo cáo quá lớn. Chọn PDF hoặc thu hẹp khoảng ngày."), 413),
                            (exporter.ReportExportUnavailable("Chưa có phông chữ tiếng Việt."), 503)]:
        def fail(*_args):
            raise error
        monkeypatch.setattr(exporter, "render_training_report", fail)
        response = client.get("/v2/training/reports/alice/export?format=png")
        assert response.status_code == expected
        assert response.json()["detail"] == str(error)
    assert client.get("/v2/training/reports/alice/export?format=html").status_code == 422


def test_aggregate_retains_missing_scores_without_fabricated_zero():
    details = [{"cycle_id": "one", "cycle_name": "Một", "end_date": date(2026, 10, 10),
                **{key: None for key in SCORE_KEYS}},
               {"cycle_id": "one", "cycle_name": "Một", "end_date": date(2026, 10, 10),
                **{key: 4 for key in SCORE_KEYS}, "craft_score": Decimal("4.125"), "attitude_score": None}]
    result = training._report_evaluation_averages(details)[0]
    assert result["craft"] == 4.13
    assert result["attitude"] is None
    assert result["conduct"] == 4
    assert result["communication"] == 4


def test_export_filename_handles_vietnamese_quotes_safely(report_client, monkeypatch):
    import vera_web_v2_training_report_export as exporter
    from urllib.parse import quote
    client, engine, _ = report_client
    username = 'Đỗ "Thảo"'
    with engine.begin() as conn:
        insert(conn, "employees", username=username, full_name=username, role="nhanvien", payload='{"employment_status":"active"}')
        session(conn, "vietnamese-name", "2026-10-10", employee=username)
    monkeypatch.setattr(exporter, "render_training_report", lambda *_args: b"synthetic-pdf")
    response = client.get(f"/v2/training/reports/{quote(username, safe='')}/export?format=pdf")
    assert response.status_code == 200, response.text
    assert response.headers["content-disposition"] == (
        'attachment; filename="VERA_DaoTao.pdf"; filename*=UTF-8\'\''
        + quote("Đỗ _Thảo__VERA_DaoTao.pdf", safe="")
    )


def test_untrained_roster_is_all_time_disjoint_active_authorized_and_read_only(report_client):
    client, engine, state = report_client
    with engine.begin() as conn:
        session(conn, "old-training", "2020-02-29", employee="empty")
        evaluation(conn, "cancelled-result", "cancelled", "2026-10-10", employee="leader2", status="cancelled")
    state["sql"].clear()
    data = get(client, "/v2/training/report-employees", date_from="2026-12-01", date_to="2026-12-31")
    assert data["employees"] == []
    assert data["untrained_scope"] == "all_time"
    assert {person["username"] for person in data["untrained_employees"]} == {"admin", "leader", "leader2", "manager", "draft"}
    assert all(sql.lstrip().upper().startswith("SELECT") for sql in state["sql"])
    all_time = get(client, "/v2/training/report-employees")
    assert data["untrained_employees"] == all_time["untrained_employees"]
    assert not ({p["username"] for p in all_time["employees"]} & {p["username"] for p in all_time["untrained_employees"]})
    # No direct/effective role widening, inactive staff, or archived identities.
    state["identity"] = Identity(employee_username="leader", role="leader")
    assert [p["username"] for p in get(client, "/v2/training/report-employees")["untrained_employees"]] == ["draft"]
    state["identity"] = Identity(employee_username="manager", role="quanly")
    assert get(client, "/v2/training/report-employees")["untrained_employees"] == []
    state["identity"] = Identity(employee_username="alice", role="nhanvien")
    assert get(client, "/v2/training/report-employees")["untrained_employees"] == []


@pytest.mark.parametrize("file_format", ["pdf", "png"])
def test_report_filename_uses_display_name_preserves_unicode_and_is_one_safe_basename(file_format):
    from pathlib import PureWindowsPath
    import unicodedata
    assert training._training_report_filename({"username": "account-id", "full_name": "Thảo Linh"}, file_format) == f"Thảo Linh_VERA_DaoTao.{file_format}"
    assert training._training_report_filename({"username": "account-id", "full_name": unicodedata.normalize("NFD", "Thảo Linh")}, file_format) == f"Thảo Linh_VERA_DaoTao.{file_format}"
    name = training._training_report_filename({"full_name": '  ../Đỗ "Thảo"\\x\r\n:tail?*  '}, file_format)
    assert name == f"_Đỗ _Thảo__x___tail___VERA_DaoTao.{file_format}"
    assert PureWindowsPath(name).name == name
    assert not any(ord(char) < 32 for char in name)
    long_name = training._training_report_filename({"full_name": "Thảo🙂" * 100}, file_format)
    assert len(long_name.encode("utf-8")) < 255
    assert training._training_report_filename({"full_name": "..."}, file_format) == f"NhanVien_VERA_DaoTao.{file_format}"


def test_no_record_bucket_stays_disjoint_if_a_record_disappears_between_reads(report_client, monkeypatch):
    client, _, _ = report_client
    original = training._report_employees
    calls = 0
    def changing_read(conn, catalog, date_from=None, date_to=None):
        nonlocal calls
        calls += 1
        return original(conn, catalog, date_from, date_to) if calls == 1 else []
    monkeypatch.setattr(training, "_report_employees", changing_read)
    data = get(client, "/v2/training/report-employees", date_from="2026-10-10", date_to="2026-10-10")
    assert not ({p["username"] for p in data["employees"]} & {p["username"] for p in data["untrained_employees"]})
