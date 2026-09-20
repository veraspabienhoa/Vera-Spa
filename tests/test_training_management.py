from datetime import date, time
from pathlib import Path

import pytest
from pydantic import ValidationError

from vera_web_v2_training import EvaluationInput, GRADE_SCORE, TrainingSessionInput


ROOT = Path(__file__).resolve().parents[1]


def test_skill_grade_scale_is_ordered_for_progress_chart():
    assert [GRADE_SCORE[key] for key in ["E", "D", "C", "B", "A", "A+"]] == [1, 2, 3, 4, 5, 6]


def test_training_session_accepts_defined_grade_and_attitude():
    item = TrainingSessionInput(
        employee_username="ktv01", training_date=date(2026, 9, 20),
        start_time=time(9), end_time=time(10), learning_attitude="Tốt", skill_grade="A+",
    )
    assert item.skill_grade == "A+"
    with pytest.raises(ValidationError):
        TrainingSessionInput(
            employee_username="ktv01", training_date=date(2026, 9, 20),
            start_time=time(9), end_time=time(10), learning_attitude="Xuất sắc", skill_grade="S",
        )


def test_evaluation_scores_are_limited_to_five_point_scale():
    valid = dict(
        craft_score=5, communication_score=4, attitude_score=3, discipline_score=2,
        appearance_score=5, hygiene_score=4, attendance_score=3,
    )
    assert EvaluationInput(**valid).craft_score == 5
    with pytest.raises(ValidationError):
        EvaluationInput(**{**valid, "craft_score": 6})


def test_training_feature_is_wired_through_backend_permissions_and_frontend():
    api = (ROOT / "vera_web_v2_api.py").read_text(encoding="utf-8")
    permissions = (ROOT / "vera_web_v2_permissions.py").read_text(encoding="utf-8")
    app = (ROOT / "web-v2/src/App.jsx").read_text(encoding="utf-8")
    shell = (ROOT / "web-v2/src/components/AppShell.jsx").read_text(encoding="utf-8")
    client = (ROOT / "web-v2/src/lib/api.js").read_text(encoding="utf-8")
    assert "install_training_routes(" in api
    for feature in ["training_view", "training_session_create", "training_session_update", "training_evaluate", "training_admin"]:
        assert f'"{feature}"' in permissions
    assert "page === 'training'" in app
    assert "permission: 'training_view'" in shell
    assert "trainingBootstrap" in client and "saveTrainingEvaluation" in client


def test_training_backend_enforces_scope_and_evaluator_ownership():
    source = (ROOT / "vera_web_v2_training.py").read_text(encoding="utf-8")
    assert "if not _scope_allowed(conn, ident, body.employee_username)" in source
    assert 'assignment["evaluator_username"]' in source
    assert 'assignment["cycle_status"] != "active"' in source
