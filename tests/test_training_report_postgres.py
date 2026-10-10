"""Native PostgreSQL dates, aggregation parity and read-only training reports."""
from datetime import date
import json
import os
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

import vera_web_v2_training as training
from test_training_report_routes import Identity, evaluation, session


@pytest.fixture
def training_database():
    url = os.getenv("VERA_TEST_POSTGRES_URL")
    if not url:
        pytest.skip("VERA_TEST_POSTGRES_URL is required for real PostgreSQL tests")
    schema = "training_report_test_" + uuid4().hex
    admin = create_engine(url)
    with admin.begin() as conn:
        conn.execute(text(f"CREATE SCHEMA {schema}"))
    engine = create_engine(url, connect_args={"options": f"-csearch_path={schema}"})
    try:
        with engine.begin() as conn:
            conn.execute(text("CREATE TABLE employees (username TEXT, full_name TEXT, role TEXT, payload JSONB)"))
            for username, role in (("leader", "leader"), ("leader2", "leader"), ("alice", "nhanvien"), ("betty", "letan"), ("empty", "nhanvien")):
                conn.execute(text("INSERT INTO employees VALUES (:name,:name,:role,CAST(:payload AS jsonb))"),
                             {"name": username, "role": role, "payload": json.dumps({})})
            training._migrate_read_schema(conn)
            # Use the real table defaults/required audit fields. The fixture
            # helper's statements below supply no identity or sensitive records.
            conn.execute(text("ALTER TABLE vera_training_session ALTER COLUMN updated_by SET DEFAULT 'synthetic'"))
            conn.execute(text("ALTER TABLE vera_evaluation_cycle ALTER COLUMN created_by SET DEFAULT 'synthetic'"))
            conn.execute(text("ALTER TABLE vera_employee_evaluation ALTER COLUMN updated_by SET DEFAULT 'synthetic'"))
            for index, day in enumerate(("2024-02-28", "2024-02-29", "2024-03-01")):
                session(conn, "daily-" + day, day)
                evaluation(conn, "eval-" + day, day, day, score=5-index)
            evaluation(conn, "other-evaluator", "2024-02-29", "2024-02-29", evaluator="leader2", score=2, comments="Cần luyện thêm")
            session(conn, "outside-role", "2024-02-29", employee="betty", trainer="leader")
            conn.execute(text("UPDATE vera_evaluation_cycle SET start_date='2024-02-01'"))
        yield engine
    finally:
        engine.dispose()
        with admin.begin() as conn:
            conn.execute(text(f"DROP SCHEMA {schema} CASCADE"))
        admin.dispose()


def test_native_dates_filter_roster_and_all_sections_in_read_only_transaction(training_database):
    with training_database.begin() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        day = date(2024, 2, 29)
        permitted = training._training_employee_catalog(conn, Identity(employee_username="leader", role="leader"))
        roster = training._report_employees(conn, permitted, day, day)
        assert [row["username"] for row in roster] == ["alice"]
        report = training._read_training_report(conn, roster[0], date_from=day, date_to=day, all_history=True)
        assert [row["training_date"] for row in report["progress"]] == [day]
        assert [row["end_date"] for row in report["evaluations"]] == [day]
        assert report["latest_radar"]["craft"] == 3.0
        assert report["history_total"] == len(report["history"]) == 3
        assert all(row["date"] == day for row in report["history"])
        # Legacy SQL averaging and the filtered DTO use the same semantics.
        expected = conn.execute(text("""
            SELECT ROUND(AVG(ev.craft_score),2),
                   ROUND(AVG((ev.discipline_score+ev.appearance_score+ev.hygiene_score+ev.attendance_score)/4.0),2)
            FROM vera_evaluation_assignment a
            JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
            WHERE a.cycle_id='2024-02-29'
        """)).one()
        assert report["latest_radar"]["craft"] == float(expected[0])
        assert report["latest_radar"]["conduct"] == float(expected[1])


def test_native_report_filters_recompute_latest_without_missing_or_outside_records(training_database):
    with training_database.begin() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        report = training._read_training_report(conn, {"username": "alice"}, q="Cần luyện thêm",
            date_from=date(2024, 2, 1), date_to=date(2024, 2, 29), all_history=True)
        assert report["progress"] == []
        assert len(report["evaluation_details"]) == 1
        assert report["latest_radar"]["craft"] == 2.0
        assert report["latest_radar"]["end_date"] == date(2024, 2, 29)
        assert len(report["history"]) == report["history_total"] == 1
