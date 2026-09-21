from datetime import date, time
from pathlib import Path

import pytest
from pydantic import ValidationError

from vera_web_v2_training import (
    EvaluationInput, GRADE_SCORE, ROLE_TARGETS, TrainingSessionInput,
    _rating_from_grade, _rating_from_scores,
)


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


def test_training_backend_enforces_role_pairs_and_evaluator_ownership():
    source = (ROOT / "vera_web_v2_training.py").read_text(encoding="utf-8")
    assert ROLE_TARGETS == {"leader": {"nhanvien"}, "quanly": {"letan", "locker", "tapvu"}}
    assert '"training_students": training_students' in source
    assert 'lower(ts.trainer_username)=lower(:viewer)' in source
    assert 'assignment["evaluator_username"]' in source
    assert "_require_assessment_pair(" in source
    assert "'đang làm việc', 'active'" in source
    assert 'assignment["cycle_status"] != "active"' in source


def test_training_history_filters_and_notifications_are_wired():
    backend = (ROOT / "vera_web_v2_training.py").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/TrainingPage.jsx").read_text(encoding="utf-8")
    popup = (ROOT / "web-v2/src/components/PopupNotifications.jsx").read_text(encoding="utf-8")
    for value in ["vera_training_notification_recipient", "vera_training_notification", '"history": history']:
        assert value in backend
    for endpoint in ["notification-recipients", "notifications/{notification_id}/detail"]:
        assert endpoint in backend
    assert "Chỉ hiển thị Leader" in page and "Chỉ hiển thị Quản lý" in page
    assert "Lịch sử Đào tạo & Đánh giá" in page
    assert "trainingNotificationDetail" in popup


def test_training_ratings_exports_and_cycle_notifications_are_wired():
    backend = (ROOT / "vera_web_v2_training.py").read_text(encoding="utf-8")
    page = (ROOT / "web-v2/src/pages/TrainingPage.jsx").read_text(encoding="utf-8")
    assert _rating_from_grade("A+") == "excellent"
    assert _rating_from_grade("B") == "good"
    assert _rating_from_grade("C") == "average"
    assert _rating_from_grade("E") == "weak"
    scores = {key: 5 for key in (
        "craft_score", "communication_score", "attitude_score", "discipline_score",
        "appearance_score", "hygiene_score", "attendance_score",
    )}
    assert _rating_from_scores(scores) == "excellent"
    assert "_dispatch_cycle_notifications" in backend
    assert 'export.{file_format}' in backend
    assert "UsernameAutocomplete" in page
    assert "Xuất sắc" in page and "Ảnh PNG" in page


def test_training_ui_uses_unrestricted_student_directory_for_daily_log():
    source = (ROOT / "web-v2/src/pages/TrainingPage.jsx").read_text(encoding="utf-8")
    assert "data?.training_students?.map" in source
    assert "Học viên được đào tạo" in source


def test_date_picker_anchor_and_requested_layout_order_are_wired():
    styles = (ROOT / "web-v2/src/styles.css").read_text(encoding="utf-8")
    revenue = (ROOT / "web-v2/src/pages/RevenuePage.jsx").read_text(encoding="utf-8")
    employee = (ROOT / "web-v2/src/pages/EmployeeManagementEnhancements.jsx").read_text(encoding="utf-8")
    assert ".vera-date-input > .vera-native-date-picker {\n  position: absolute;" in styles
    assert "left: -10000px" not in styles
    assert "Doanh thu theo bộ lọc" in revenue and "Chi phí theo bộ lọc" in revenue
    assert employee.index("<KtvShiftSettingsPanel") < employee.index("<ShiftBreakSettingsPanel")
