"""Training sessions, periodic employee evaluations, and analytics for Web V2."""
from __future__ import annotations

from datetime import date, datetime, time
from io import BytesIO
from pathlib import Path
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, Query, Response
from PIL import Image, ImageDraw, ImageFont
from pydantic import BaseModel, Field
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.pdfgen import canvas
from sqlalchemy import text


GRADE_SCORE = {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "A+": 6}
RATING_LABELS = {"excellent": "Xuất sắc", "good": "Tốt", "average": "Trung bình", "weak": "Yếu"}


class TrainingSessionInput(BaseModel):
    employee_username: str = Field(min_length=1, max_length=200)
    training_date: date
    start_time: time
    end_time: time
    topic: str = Field(default="", max_length=300)
    learning_attitude: Literal["Tốt", "Khá", "Trung bình", "Kém"]
    skill_grade: Literal["A+", "A", "B", "C", "D", "E"]
    strengths: str = Field(default="", max_length=3000)
    improvements: str = Field(default="", max_length=3000)
    notes: str = Field(default="", max_length=5000)


class CycleInput(BaseModel):
    name: str = Field(min_length=1, max_length=300)
    start_date: date
    end_date: date
    employee_usernames: list[str] = Field(min_length=1)
    evaluator_usernames: list[str] = Field(min_length=1)
    instructions: str = Field(default="", max_length=5000)


class EvaluationInput(BaseModel):
    craft_score: int = Field(ge=1, le=5)
    communication_score: int = Field(ge=1, le=5)
    attitude_score: int = Field(ge=1, le=5)
    discipline_score: int = Field(ge=1, le=5)
    appearance_score: int = Field(ge=1, le=5)
    hygiene_score: int = Field(ge=1, le=5)
    attendance_score: int = Field(ge=1, le=5)
    strengths: str = Field(default="", max_length=3000)
    improvements: str = Field(default="", max_length=3000)
    comments: str = Field(default="", max_length=5000)
    submit: bool = False


class ScopeInput(BaseModel):
    trainer_username: str = Field(min_length=1, max_length=200)
    employee_usernames: list[str]


class NotificationRecipientsInput(BaseModel):
    usernames: list[str]


ROLE_TARGETS = {
    "leader": {"nhanvien"},
    "quanly": {"letan", "locker", "tapvu"},
}
ACTIVE_EMPLOYEE_SQL = "lower(COALESCE(e.payload->>'Trạng thái làm việc', e.payload->>'employment_status', 'Đang làm việc')) IN ('đang làm việc', 'active')"


def _schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_training_scope (
            trainer_username TEXT NOT NULL,
            employee_username TEXT NOT NULL,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            assigned_by TEXT NOT NULL,
            assigned_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            PRIMARY KEY (trainer_username, employee_username)
        );
        CREATE TABLE IF NOT EXISTS vera_training_session (
            id TEXT PRIMARY KEY,
            employee_username TEXT NOT NULL,
            trainer_username TEXT NOT NULL,
            training_date DATE NOT NULL,
            start_time TIME NOT NULL,
            end_time TIME NOT NULL,
            topic TEXT NOT NULL DEFAULT '',
            learning_attitude TEXT NOT NULL,
            skill_grade TEXT NOT NULL,
            strengths TEXT NOT NULL DEFAULT '',
            improvements TEXT NOT NULL DEFAULT '',
            notes TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'submitted',
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vera_evaluation_cycle (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            start_date DATE NOT NULL,
            end_date DATE NOT NULL,
            instructions TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT 'draft',
            created_by TEXT NOT NULL,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            activated_at TIMESTAMPTZ,
            closed_at TIMESTAMPTZ
        );
        CREATE TABLE IF NOT EXISTS vera_evaluation_assignment (
            id TEXT PRIMARY KEY,
            cycle_id TEXT NOT NULL REFERENCES vera_evaluation_cycle(id) ON DELETE CASCADE,
            employee_username TEXT NOT NULL,
            evaluator_username TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'pending',
            UNIQUE (cycle_id, employee_username, evaluator_username)
        );
        CREATE TABLE IF NOT EXISTS vera_employee_evaluation (
            assignment_id TEXT PRIMARY KEY REFERENCES vera_evaluation_assignment(id) ON DELETE CASCADE,
            craft_score SMALLINT NOT NULL,
            communication_score SMALLINT NOT NULL,
            attitude_score SMALLINT NOT NULL,
            discipline_score SMALLINT NOT NULL,
            appearance_score SMALLINT NOT NULL,
            hygiene_score SMALLINT NOT NULL,
            attendance_score SMALLINT NOT NULL,
            strengths TEXT NOT NULL DEFAULT '',
            improvements TEXT NOT NULL DEFAULT '',
            comments TEXT NOT NULL DEFAULT '',
            submitted_at TIMESTAMPTZ,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            updated_by TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS vera_training_audit (
            id BIGSERIAL PRIMARY KEY,
            entity_type TEXT NOT NULL,
            entity_id TEXT NOT NULL,
            action TEXT NOT NULL,
            actor_username TEXT NOT NULL,
            detail JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vera_training_notification_recipient (
            username TEXT PRIMARY KEY,
            active BOOLEAN NOT NULL DEFAULT TRUE,
            updated_by TEXT NOT NULL,
            updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE TABLE IF NOT EXISTS vera_training_notification (
            id TEXT PRIMARY KEY,
            recipient_username TEXT NOT NULL,
            reference_type TEXT NOT NULL,
            reference_id TEXT NOT NULL,
            title TEXT NOT NULL,
            body TEXT NOT NULL,
            is_read BOOLEAN NOT NULL DEFAULT FALSE,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            read_at TIMESTAMPTZ,
            UNIQUE(recipient_username, reference_type, reference_id)
        );
        CREATE INDEX IF NOT EXISTS idx_training_session_employee_date
            ON vera_training_session(employee_username, training_date DESC);
        CREATE INDEX IF NOT EXISTS idx_training_session_trainer_date
            ON vera_training_session(trainer_username, training_date DESC);
        CREATE INDEX IF NOT EXISTS idx_training_assignment_evaluator
            ON vera_evaluation_assignment(evaluator_username, status);
        CREATE INDEX IF NOT EXISTS idx_training_assignment_employee_status
            ON vera_evaluation_assignment(employee_username, status);
        CREATE INDEX IF NOT EXISTS idx_evaluation_cycle_date_range
            ON vera_evaluation_cycle(start_date, end_date);
        CREATE INDEX IF NOT EXISTS idx_employee_evaluation_submitted
            ON vera_employee_evaluation(submitted_at DESC);
        CREATE INDEX IF NOT EXISTS idx_training_notification_inbox
            ON vera_training_notification(recipient_username, is_read, created_at DESC);
    """))


def _rows(result) -> list[dict[str, Any]]:
    return [dict(row) for row in result.mappings().all()]


def _is_admin(ident) -> bool:
    return str(ident.role or "").lower() == "admin"


def _scope_allowed(conn, ident, employee: str) -> bool:
    if _is_admin(ident):
        return True
    return bool(conn.execute(text("""
        SELECT 1 FROM vera_training_scope
        WHERE active=TRUE AND lower(trainer_username)=lower(:trainer)
          AND lower(employee_username)=lower(:employee)
    """), {"trainer": ident.employee_username, "employee": employee}).scalar_one_or_none())


def _require_admin(ident) -> None:
    if not _is_admin(ident):
        raise HTTPException(403, "Chỉ Admin được thực hiện thao tác này.")


def _employee(conn, username: str) -> dict[str, Any] | None:
    row = conn.execute(text("""
        SELECT e.username, e.username full_name,
               lower(COALESCE(e.role,'')) role,
               COALESCE(e.payload->>'Trạng thái làm việc',e.payload->>'employment_status','Đang làm việc') employment_status
        FROM employees e WHERE lower(e.username)=lower(:username)
          AND COALESCE(e.payload->>'__deleted','false') <> 'true'
    """), {"username": username}).mappings().first()
    return dict(row) if row else None


def _can_assess(evaluator_role: str, evaluatee_role: str, *, admin_override: bool = False) -> bool:
    if admin_override and evaluator_role == "admin":
        return True
    return evaluatee_role in ROLE_TARGETS.get(evaluator_role, set())


def _require_assessment_pair(conn, evaluator_username: str, evaluatee_username: str, *, admin_override: bool = False) -> tuple[dict, dict]:
    evaluator = _employee(conn, evaluator_username)
    evaluatee = _employee(conn, evaluatee_username)
    if not evaluator or not evaluatee:
        raise HTTPException(404, "Không tìm thấy người đánh giá hoặc nhân viên được đánh giá.")
    if str(evaluatee["employment_status"]).strip().lower() not in {"đang làm việc", "active"}:
        raise HTTPException(409, "Không thể đào tạo/đánh giá nhân viên đã nghỉ hoặc tạm nghỉ việc.")
    if not _can_assess(evaluator["role"], evaluatee["role"], admin_override=admin_override):
        raise HTTPException(403, "Sai thẩm quyền: Leader chỉ phụ trách Nhân viên; Quản lý phụ trách Lễ tân, Locker và Tạp vụ.")
    return evaluator, evaluatee


def _dispatch_completed_notifications(conn, *, reference_type: str, reference_id: str, evaluatee: dict, evaluator: dict) -> int:
    recipients = {
        str(row[0]) for row in conn.execute(text("""
            SELECT e.username FROM employees e
            WHERE lower(COALESCE(e.role,''))='admin'
              AND COALESCE(e.payload->>'__deleted','false') <> 'true'
              AND """ + ACTIVE_EMPLOYEE_SQL)).all()
    }
    recipients.update(str(row[0]) for row in conn.execute(text("""
        SELECT username FROM vera_training_notification_recipient WHERE active=TRUE
    """)))
    recipients.add(str(evaluatee["username"]))
    label = "Đào tạo hằng ngày" if reference_type == "daily_training" else "Đánh giá tổng hợp"
    title = f"{label} đã hoàn thành"
    body = f"{evaluatee['full_name']} · Người thực hiện: {evaluator['full_name']}"
    for recipient in {item.strip() for item in recipients if item and item.strip()}:
        conn.execute(text("""
            INSERT INTO vera_training_notification(id,recipient_username,reference_type,reference_id,title,body)
            VALUES (:id,:recipient,:reference_type,:reference_id,:title,:body)
            ON CONFLICT (recipient_username,reference_type,reference_id) DO NOTHING
        """), {"id": str(uuid4()), "recipient": recipient, "reference_type": reference_type,
                 "reference_id": reference_id, "title": title, "body": body})
    return len(recipients)


def _dispatch_cycle_notifications(conn, *, cycle_id: str, cycle_name: str) -> int:
    rows = conn.execute(text("""
        SELECT employee_username,evaluator_username FROM vera_evaluation_assignment
        WHERE cycle_id=:cycle
    """), {"cycle": cycle_id}).mappings().all()
    recipients = {str(item["employee_username"]) for item in rows}
    recipients.update(str(item["evaluator_username"]) for item in rows)
    for recipient in recipients:
        conn.execute(text("""
            INSERT INTO vera_training_notification(
                id,recipient_username,reference_type,reference_id,title,body)
            VALUES (:id,:recipient,'evaluation_cycle',:cycle,'Đợt đánh giá mới',:body)
            ON CONFLICT (recipient_username,reference_type,reference_id) DO NOTHING
        """), {"id": str(uuid4()), "recipient": recipient, "cycle": cycle_id,
                 "body": f"Bạn được phân công trong đợt: {cycle_name}"})
    return len(recipients)


def _rating_from_grade(grade: str) -> str:
    if grade in {"A+", "A"}:
        return "excellent"
    if grade == "B":
        return "good"
    if grade == "C":
        return "average"
    return "weak"


def _rating_from_scores(item: dict[str, Any]) -> str:
    values = [float(item.get(key) or 0) for key in (
        "craft_score", "communication_score", "attitude_score", "discipline_score",
        "appearance_score", "hygiene_score", "attendance_score",
    )]
    average = sum(values) / len(values) if values else 0
    return "excellent" if average >= 4.5 else "good" if average >= 3.5 else "average" if average >= 2.5 else "weak"


def _font_path(bold: bool = False) -> Path | None:
    names = ["DejaVuSans-Bold.ttf"] if bold else ["DejaVuSans.ttf"]
    roots = [Path("/usr/share/fonts/truetype/dejavu"), Path("/usr/share/fonts/truetype/freefont")]
    for root in roots:
        for name in names:
            path = root / name
            if path.exists():
                return path
    return None


def _export_evaluation_png(item: dict[str, Any]) -> bytes:
    image = Image.new("RGB", (1400, 1050), "white")
    draw = ImageDraw.Draw(image)
    regular_path, bold_path = _font_path(), _font_path(True)
    regular = ImageFont.truetype(str(regular_path), 30) if regular_path else ImageFont.load_default()
    small = ImageFont.truetype(str(regular_path), 25) if regular_path else ImageFont.load_default()
    bold = ImageFont.truetype(str(bold_path or regular_path), 42) if (bold_path or regular_path) else ImageFont.load_default()
    draw.rectangle((0, 0, 1400, 145), fill="#173d2f")
    draw.text((60, 42), "VERA SPA · KẾT QUẢ ĐÁNH GIÁ", font=bold, fill="white")
    draw.text((60, 180), f"Nhân viên: {item['employee_username']}", font=regular, fill="#173d2f")
    draw.text((60, 225), f"Người đánh giá: {item['evaluator_username']}", font=regular, fill="#173d2f")
    draw.text((60, 270), f"Đợt: {item['cycle_name']} · {item['end_date']}", font=regular, fill="#173d2f")
    scores = [
        ("Tay nghề", item["craft_score"]), ("Giao tiếp", item["communication_score"]),
        ("Thái độ", item["attitude_score"]), ("Kỷ luật", item["discipline_score"]),
        ("Ngoại hình", item["appearance_score"]), ("Vệ sinh", item["hygiene_score"]),
        ("Chuyên cần", item["attendance_score"]),
    ]
    y = 355
    for label, score in scores:
        draw.text((70, y), label, font=small, fill="#29483d")
        draw.rounded_rectangle((330, y, 1180, y + 30), radius=14, fill="#e5eee9")
        draw.rounded_rectangle((330, y, 330 + int(850 * float(score) / 5), y + 30), radius=14, fill="#c99b32")
        draw.text((1210, y - 3), f"{score}/5", font=small, fill="#173d2f")
        y += 65
    draw.text((70, 835), f"Xếp loại: {RATING_LABELS[_rating_from_scores(item)]}", font=regular, fill="#173d2f")
    notes = str(item.get("comments") or item.get("improvements") or item.get("strengths") or "Không có nhận xét.")
    draw.text((70, 895), "Nhận xét: " + notes[:100], font=small, fill="#3f5149")
    output = BytesIO(); image.save(output, format="PNG", optimize=True); return output.getvalue()


def _export_evaluation_pdf(item: dict[str, Any]) -> bytes:
    output = BytesIO()
    regular_path, bold_path = _font_path(), _font_path(True)
    regular_name, bold_name = "Helvetica", "Helvetica-Bold"
    if regular_path:
        regular_name = "VeraEvaluation"
        if regular_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(regular_name, str(regular_path)))
    if bold_path:
        bold_name = "VeraEvaluationBold"
        if bold_name not in pdfmetrics.getRegisteredFontNames():
            pdfmetrics.registerFont(TTFont(bold_name, str(bold_path)))
    pdf = canvas.Canvas(output, pagesize=(595, 842))
    pdf.setFillColor("#173d2f"); pdf.rect(0, 760, 595, 82, fill=1, stroke=0)
    pdf.setFillColor("white"); pdf.setFont(bold_name, 18); pdf.drawString(38, 795, "VERA SPA · KẾT QUẢ ĐÁNH GIÁ")
    pdf.setFillColor("#173d2f"); pdf.setFont(regular_name, 11)
    pdf.drawString(38, 730, f"Nhân viên: {item['employee_username']}")
    pdf.drawString(38, 710, f"Người đánh giá: {item['evaluator_username']}")
    pdf.drawString(38, 690, f"Đợt: {item['cycle_name']} · {item['end_date']}")
    scores = [("Tay nghề", item["craft_score"]), ("Giao tiếp", item["communication_score"]),
              ("Thái độ", item["attitude_score"]), ("Kỷ luật", item["discipline_score"]),
              ("Ngoại hình", item["appearance_score"]), ("Vệ sinh", item["hygiene_score"]),
              ("Chuyên cần", item["attendance_score"])]
    y = 640
    for label, score in scores:
        pdf.setFont(regular_name, 10); pdf.setFillColor("#29483d"); pdf.drawString(42, y, label)
        pdf.setFillColor("#e5eee9"); pdf.roundRect(150, y - 2, 330, 12, 6, fill=1, stroke=0)
        pdf.setFillColor("#c99b32"); pdf.roundRect(150, y - 2, 330 * float(score) / 5, 12, 6, fill=1, stroke=0)
        pdf.setFillColor("#173d2f"); pdf.drawString(495, y, f"{score}/5"); y -= 45
    pdf.setFont(bold_name, 12); pdf.drawString(42, 300, f"Xếp loại: {RATING_LABELS[_rating_from_scores(item)]}")
    pdf.setFont(regular_name, 10)
    notes = str(item.get("comments") or item.get("improvements") or item.get("strengths") or "Không có nhận xét.")
    pdf.drawString(42, 272, "Nhận xét: " + notes[:95])
    pdf.showPage(); pdf.save(); return output.getvalue()


def _audit(conn, entity_type: str, entity_id: str, action: str, actor: str, detail: dict | None = None) -> None:
    conn.execute(text("""
        INSERT INTO vera_training_audit(entity_type, entity_id, action, actor_username, detail)
        VALUES (:entity_type, :entity_id, :action, :actor, CAST(:detail AS jsonb))
    """), {"entity_type": entity_type, "entity_id": entity_id, "action": action,
             "actor": actor, "detail": __import__("json").dumps(detail or {}, ensure_ascii=False)})


def _report_employees(conn, employees):
    """Only permitted employees with daily or submitted comprehensive results."""
    usernames = {
        str(row[0]).casefold()
        for row in conn.execute(text("""
            SELECT lower(employee_username) FROM vera_training_session
            UNION
            SELECT lower(a.employee_username)
            FROM vera_evaluation_assignment a
            JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
            WHERE a.status='submitted'
        """))
    }
    return [employee for employee in employees if employee["username"].casefold() in usernames]


def install_training_routes(
    app, *, engine_instance: Callable[[], Any], current_identity: Callable,
    require_feature: Callable, identity_type: Any,
) -> None:
    @app.get("/v2/training/bootstrap")
    def training_bootstrap(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn)
            require_feature(conn, ident, "training_view")
            viewer_role = str(ident.role or "").lower()
            allowed_roles = ROLE_TARGETS.get(viewer_role, set())
            role_filter = "" if _is_admin(ident) else (
                " AND lower(COALESCE(e.role,'')) IN (" + ",".join(f"'{role}'" for role in sorted(allowed_roles)) + ")"
                if allowed_roles else " AND FALSE"
            )
            employees = _rows(conn.execute(text("""
                SELECT e.username, e.username AS full_name,
                       lower(COALESCE(e.role,'')) AS role
                FROM employees e
                WHERE COALESCE(e.payload->>'__deleted','false') <> 'true'
                  AND """ + ACTIVE_EMPLOYEE_SQL + role_filter + " ORDER BY lower(COALESCE(NULLIF(e.full_name,''), e.username))"),
                {"viewer": ident.employee_username}))
            training_students = employees
            sessions_filter = "" if _is_admin(ident) else """
                WHERE lower(ts.trainer_username)=lower(:viewer)
            """
            sessions = _rows(conn.execute(text("""
                SELECT ts.*, ts.employee_username employee_name,
                       ts.trainer_username trainer_name,
                       lower(COALESCE(t.role,'')) evaluator_role
                FROM vera_training_session ts
                LEFT JOIN employees e ON lower(e.username)=lower(ts.employee_username)
                LEFT JOIN employees t ON lower(t.username)=lower(ts.trainer_username)
            """ + sessions_filter + (" WHERE " if not sessions_filter else " AND ") + """
                """ + ACTIVE_EMPLOYEE_SQL + """
                ORDER BY ts.training_date DESC, ts.start_time DESC LIMIT 300
            """),
                {"viewer": ident.employee_username}))
            assignments = _rows(conn.execute(text("""
                SELECT a.*, c.name cycle_name, c.start_date, c.end_date, c.status cycle_status,
                       a.employee_username employee_name,
                       a.evaluator_username evaluator_name,
                       lower(COALESCE(v.role,'')) evaluator_role,
                       ev.craft_score, ev.communication_score, ev.attitude_score,
                       ev.discipline_score, ev.appearance_score, ev.hygiene_score,
                       ev.attendance_score, ev.strengths, ev.improvements, ev.comments
                FROM vera_evaluation_assignment a
                JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
                LEFT JOIN employees e ON lower(e.username)=lower(a.employee_username)
                LEFT JOIN employees v ON lower(v.username)=lower(a.evaluator_username)
                LEFT JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
                WHERE (:admin OR lower(a.evaluator_username)=lower(:viewer))
                  AND """ + ACTIVE_EMPLOYEE_SQL + """
                ORDER BY c.end_date DESC, employee_name
            """), {"admin": _is_admin(ident), "viewer": ident.employee_username}))
            cycles = _rows(conn.execute(text("""
                SELECT c.*, COUNT(a.id)::int assignment_count,
                       COUNT(a.id) FILTER (WHERE a.status='submitted')::int submitted_count
                FROM vera_evaluation_cycle c
                LEFT JOIN vera_evaluation_assignment a ON a.cycle_id=c.id
                GROUP BY c.id ORDER BY c.created_at DESC
            """))) if _is_admin(ident) else []
            scopes = _rows(conn.execute(text("""
                SELECT s.*, s.trainer_username trainer_name,
                       s.employee_username employee_name
                FROM vera_training_scope s
                LEFT JOIN employees t ON lower(t.username)=lower(s.trainer_username)
                LEFT JOIN employees e ON lower(e.username)=lower(s.employee_username)
                WHERE s.active=TRUE ORDER BY lower(s.trainer_username), lower(s.employee_username)
            """))) if _is_admin(ident) else []
            people = _rows(conn.execute(text("""
                SELECT username, username full_name, lower(COALESCE(role,'')) role
                FROM employees e WHERE COALESCE(payload->>'__deleted','false') <> 'true'
                  AND """ + ACTIVE_EMPLOYEE_SQL + """
                ORDER BY lower(COALESCE(NULLIF(full_name,''),username))
            """))) if _is_admin(ident) else employees
            evaluators = _rows(conn.execute(text("""
                SELECT e.username,e.username full_name,lower(COALESCE(e.role,'')) role
                FROM employees e WHERE lower(COALESCE(e.role,'')) IN ('leader','quanly')
                  AND COALESCE(e.payload->>'__deleted','false') <> 'true' AND """ + ACTIVE_EMPLOYEE_SQL + """
                ORDER BY role,lower(COALESCE(NULLIF(e.full_name,''),e.username))
            """)))
            notifications = _rows(conn.execute(text("""
                SELECT id,title,body,reference_type,reference_id,is_read,created_at
                FROM vera_training_notification
                WHERE lower(recipient_username)=lower(:viewer)
                ORDER BY created_at DESC LIMIT 50
            """), {"viewer": ident.employee_username}))
            notification_recipients = _rows(conn.execute(text("""
                SELECT r.username,r.username full_name
                FROM vera_training_notification_recipient r
                LEFT JOIN employees e ON lower(e.username)=lower(r.username)
                WHERE r.active=TRUE ORDER BY full_name
            """))) if _is_admin(ident) else []
            return {"employees": employees, "training_students": training_students,
                    "report_employees": _report_employees(conn, employees),
                    "people": people, "sessions": sessions,
                    "assignments": assignments, "cycles": cycles, "scopes": scopes,
                    "evaluators": evaluators, "notifications": notifications,
                    "notification_recipients": notification_recipients,
                    "is_admin": _is_admin(ident)}

    @app.post("/v2/training/sessions")
    def create_training_session(body: TrainingSessionInput, ident: identity_type = Depends(current_identity)):
        if body.end_time <= body.start_time:
            raise HTTPException(400, "Giờ kết thúc phải sau giờ bắt đầu.")
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_session_create")
            evaluator, evaluatee = _require_assessment_pair(
                conn, ident.employee_username, body.employee_username, admin_override=True,
            )
            session_id = str(uuid4())
            params = body.model_dump(); params.update({"id": session_id, "trainer": ident.employee_username})
            conn.execute(text("""
                INSERT INTO vera_training_session(
                    id, employee_username, trainer_username, training_date, start_time, end_time,
                    topic, learning_attitude, skill_grade, strengths, improvements, notes, status, updated_by)
                VALUES (:id,:employee_username,:trainer,:training_date,:start_time,:end_time,
                    :topic,:learning_attitude,:skill_grade,:strengths,:improvements,:notes,'completed',:trainer)
            """), params)
            notified = _dispatch_completed_notifications(
                conn, reference_type="daily_training", reference_id=session_id,
                evaluatee=evaluatee, evaluator=evaluator,
            )
            _audit(conn, "training_session", session_id, "create", ident.employee_username)
            return {"ok": True, "id": session_id, "notifications_created": notified}

    @app.put("/v2/training/sessions/{session_id}")
    def update_training_session(session_id: str, body: TrainingSessionInput, ident: identity_type = Depends(current_identity)):
        if body.end_time <= body.start_time:
            raise HTTPException(400, "Giờ kết thúc phải sau giờ bắt đầu.")
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_session_update")
            existing = conn.execute(text("SELECT * FROM vera_training_session WHERE id=:id FOR UPDATE"), {"id": session_id}).mappings().first()
            if not existing:
                raise HTTPException(404, "Không tìm thấy buổi đào tạo.")
            if not _is_admin(ident) and str(existing["trainer_username"]).lower() != ident.employee_username.lower():
                raise HTTPException(403, "Bạn chỉ được cập nhật nhật ký do mình nhập.")
            _require_assessment_pair(conn, ident.employee_username, body.employee_username, admin_override=True)
            params = body.model_dump(); params.update({"id": session_id, "actor": ident.employee_username})
            conn.execute(text("""
                UPDATE vera_training_session SET employee_username=:employee_username,
                    training_date=:training_date,start_time=:start_time,end_time=:end_time,
                    topic=:topic,learning_attitude=:learning_attitude,skill_grade=:skill_grade,
                    strengths=:strengths,improvements=:improvements,notes=:notes,
                    updated_at=NOW(),updated_by=:actor WHERE id=:id
            """), params)
            _audit(conn, "training_session", session_id, "update", ident.employee_username)
            return {"ok": True}

    @app.put("/v2/training/scopes")
    def save_training_scope(body: ScopeInput, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_admin"); _require_admin(ident)
            conn.execute(text("UPDATE vera_training_scope SET active=FALSE, updated_at=NOW() WHERE lower(trainer_username)=lower(:trainer)"), {"trainer": body.trainer_username})
            for employee in dict.fromkeys(body.employee_usernames):
                conn.execute(text("""
                    INSERT INTO vera_training_scope(trainer_username,employee_username,active,assigned_by)
                    VALUES (:trainer,:employee,TRUE,:actor)
                    ON CONFLICT (trainer_username,employee_username) DO UPDATE
                    SET active=TRUE, assigned_by=EXCLUDED.assigned_by, updated_at=NOW()
                """), {"trainer": body.trainer_username, "employee": employee, "actor": ident.employee_username})
            _audit(conn, "training_scope", body.trainer_username, "replace", ident.employee_username,
                   {"employees": body.employee_usernames})
            return {"ok": True}

    @app.post("/v2/training/cycles")
    def create_evaluation_cycle(body: CycleInput, ident: identity_type = Depends(current_identity)):
        if body.end_date < body.start_date:
            raise HTTPException(400, "Ngày kết thúc phải từ ngày bắt đầu trở đi.")
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_admin"); _require_admin(ident)
            cycle_id = str(uuid4())
            conn.execute(text("""
                INSERT INTO vera_evaluation_cycle(id,name,start_date,end_date,instructions,created_by)
                VALUES (:id,:name,:start_date,:end_date,:instructions,:actor)
            """), {**body.model_dump(), "id": cycle_id, "actor": ident.employee_username})
            employees = {
                username: _employee(conn, username)
                for username in dict.fromkeys(body.employee_usernames)
            }
            evaluators = {
                username: _employee(conn, username)
                for username in dict.fromkeys(body.evaluator_usernames)
            }
            for username, employee in employees.items():
                if not employee or str(employee["employment_status"]).strip().lower() not in {"đang làm việc", "active"}:
                    raise HTTPException(400, f"Nhân viên không còn làm việc: {username}")
            for username, evaluator in evaluators.items():
                if not evaluator or str(evaluator["employment_status"]).strip().lower() not in {"đang làm việc", "active"}:
                    raise HTTPException(400, f"Người đánh giá không hợp lệ: {username}")
            assigned_employees: set[str] = set()
            for employee_username, employee in employees.items():
                for evaluator_username, evaluator in evaluators.items():
                    if not _can_assess(evaluator["role"], employee["role"]):
                        continue
                    conn.execute(text("""
                        INSERT INTO vera_evaluation_assignment(id,cycle_id,employee_username,evaluator_username)
                        VALUES (:id,:cycle,:employee,:evaluator)
                    """), {"id": str(uuid4()), "cycle": cycle_id,
                             "employee": employee_username, "evaluator": evaluator_username})
                    assigned_employees.add(employee_username)
            missing = [employees[item]["full_name"] for item in employees if item not in assigned_employees]
            if missing:
                raise HTTPException(400, "Chưa chọn đúng Leader/Quản lý cho: " + ", ".join(missing))
            notified = _dispatch_cycle_notifications(conn, cycle_id=cycle_id, cycle_name=body.name)
            _audit(conn, "evaluation_cycle", cycle_id, "create", ident.employee_username)
            return {"ok": True, "id": cycle_id, "notifications_created": notified}

    @app.post("/v2/training/cycles/{cycle_id}/{action}")
    def change_cycle_status(cycle_id: str, action: Literal["activate", "close"], ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_admin"); _require_admin(ident)
            status = "active" if action == "activate" else "closed"
            stamp = "activated_at=NOW()" if action == "activate" else "closed_at=NOW()"
            changed = conn.execute(text(f"UPDATE vera_evaluation_cycle SET status=:status, {stamp} WHERE id=:id"), {"status": status, "id": cycle_id}).rowcount
            if not changed: raise HTTPException(404, "Không tìm thấy đợt đánh giá.")
            _audit(conn, "evaluation_cycle", cycle_id, action, ident.employee_username)
            return {"ok": True, "status": status}

    @app.put("/v2/training/evaluations/{assignment_id}")
    def save_evaluation(assignment_id: str, body: EvaluationInput, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_evaluate")
            assignment = conn.execute(text("""
                SELECT a.*, c.status cycle_status FROM vera_evaluation_assignment a
                JOIN vera_evaluation_cycle c ON c.id=a.cycle_id WHERE a.id=:id FOR UPDATE
            """), {"id": assignment_id}).mappings().first()
            if not assignment: raise HTTPException(404, "Không tìm thấy phiếu đánh giá.")
            if str(assignment["evaluator_username"]).lower() != ident.employee_username.lower():
                raise HTTPException(403, "Bạn không phải người được giao phiếu đánh giá này.")
            if assignment["cycle_status"] != "active":
                raise HTTPException(409, "Đợt đánh giá chưa kích hoạt hoặc đã đóng.")
            evaluator, evaluatee = _require_assessment_pair(
                conn, ident.employee_username, str(assignment["employee_username"]), admin_override=True,
            )
            was_submitted = str(assignment["status"] or "") == "submitted"
            values = body.model_dump(); values.update({"id": assignment_id, "actor": ident.employee_username})
            conn.execute(text("""
                INSERT INTO vera_employee_evaluation(
                    assignment_id,craft_score,communication_score,attitude_score,discipline_score,
                    appearance_score,hygiene_score,attendance_score,strengths,improvements,comments,
                    submitted_at,updated_by)
                VALUES (:id,:craft_score,:communication_score,:attitude_score,:discipline_score,
                    :appearance_score,:hygiene_score,:attendance_score,:strengths,:improvements,:comments,
                    CASE WHEN :submit THEN NOW() ELSE NULL END,:actor)
                ON CONFLICT (assignment_id) DO UPDATE SET
                    craft_score=EXCLUDED.craft_score, communication_score=EXCLUDED.communication_score,
                    attitude_score=EXCLUDED.attitude_score, discipline_score=EXCLUDED.discipline_score,
                    appearance_score=EXCLUDED.appearance_score, hygiene_score=EXCLUDED.hygiene_score,
                    attendance_score=EXCLUDED.attendance_score, strengths=EXCLUDED.strengths,
                    improvements=EXCLUDED.improvements, comments=EXCLUDED.comments,
                    submitted_at=CASE WHEN :submit THEN NOW() ELSE vera_employee_evaluation.submitted_at END,
                    updated_at=NOW(), updated_by=EXCLUDED.updated_by
            """), values)
            conn.execute(text("UPDATE vera_evaluation_assignment SET status=:status WHERE id=:id"),
                         {"status": "submitted" if body.submit else "draft", "id": assignment_id})
            notified = 0
            if body.submit and not was_submitted:
                notified = _dispatch_completed_notifications(
                    conn, reference_type="comprehensive_evaluation", reference_id=assignment_id,
                    evaluatee=evaluatee, evaluator=evaluator,
                )
            _audit(conn, "evaluation", assignment_id, "submit" if body.submit else "save_draft", ident.employee_username)
            return {"ok": True, "notifications_created": notified}

    @app.get("/v2/training/reports/{employee_username}")
    def employee_training_report(
        employee_username: str,
        evaluator_role: Literal["all", "leader", "quanly"] = Query(default="all"),
        q: str = Query(default="", max_length=200),
        date_from: date | None = Query(default=None),
        date_to: date | None = Query(default=None),
        rating: Literal["all", "excellent", "good", "average", "weak"] = Query(default="all"),
        page: int = Query(default=1, ge=1),
        page_size: int = Query(default=50, ge=1, le=100),
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_view")
            if not _is_admin(ident):
                _require_assessment_pair(conn, ident.employee_username, employee_username)
            role_clause = "" if evaluator_role == "all" else " AND lower(COALESCE(t.role,''))=:evaluator_role"
            progress = _rows(conn.execute(text("""
                SELECT ts.id,ts.training_date,ts.start_time,ts.end_time,ts.topic,ts.skill_grade,
                       ts.learning_attitude,ts.trainer_username,ts.trainer_username evaluator_name,
                       lower(COALESCE(t.role,'')) evaluator_role,ts.strengths,ts.improvements,ts.notes,ts.status,ts.created_at
                FROM vera_training_session ts
                LEFT JOIN employees t ON lower(t.username)=lower(ts.trainer_username)
                WHERE lower(ts.employee_username)=lower(:employee)
            """ + role_clause + """
                ORDER BY training_date, start_time
            """), {"employee": employee_username, "evaluator_role": evaluator_role}))
            for item in progress: item["skill_score"] = GRADE_SCORE.get(item["skill_grade"], 0)
            evaluations = _rows(conn.execute(text("""
                SELECT c.id cycle_id, c.name cycle_name, c.end_date,
                       ROUND(AVG(ev.craft_score),2) craft,
                       ROUND(AVG(ev.communication_score),2) communication,
                       ROUND(AVG(ev.attitude_score),2) attitude,
                       ROUND(AVG((ev.discipline_score+ev.appearance_score+ev.hygiene_score+ev.attendance_score)/4.0),2) conduct
                FROM vera_evaluation_assignment a
                JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
                JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
                LEFT JOIN employees t ON lower(t.username)=lower(a.evaluator_username)
                WHERE lower(a.employee_username)=lower(:employee) AND a.status='submitted'
            """ + role_clause + """
                GROUP BY c.id, c.name, c.end_date ORDER BY c.end_date
            """), {"employee": employee_username, "evaluator_role": evaluator_role}))
            evaluation_details = _rows(conn.execute(text("""
                SELECT a.id,c.name cycle_name,c.end_date,a.evaluator_username,
                       a.evaluator_username evaluator_name,
                       lower(COALESCE(t.role,'')) evaluator_role,a.status,ev.submitted_at,
                       ev.craft_score,ev.communication_score,ev.attitude_score,ev.discipline_score,
                       ev.appearance_score,ev.hygiene_score,ev.attendance_score,
                       ev.strengths,ev.improvements,ev.comments
                FROM vera_evaluation_assignment a
                JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
                JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
                LEFT JOIN employees t ON lower(t.username)=lower(a.evaluator_username)
                WHERE lower(a.employee_username)=lower(:employee) AND a.status='submitted'
            """ + role_clause + " ORDER BY c.end_date DESC,ev.submitted_at DESC"),
                {"employee": employee_username, "evaluator_role": evaluator_role}))
            history = [
                {"type": "daily", "date": item["training_date"], "id": item["id"],
                 "title": item["topic"] or "Đào tạo hằng ngày", "evaluator_name": item["evaluator_name"],
                 "evaluator_role": item["evaluator_role"], "rating": _rating_from_grade(item["skill_grade"]),
                 "rating_label": RATING_LABELS[_rating_from_grade(item["skill_grade"])], "detail": item}
                for item in progress
            ] + [
                {"type": "comprehensive", "date": item["end_date"], "id": item["id"],
                 "title": item["cycle_name"], "evaluator_name": item["evaluator_name"],
                 "evaluator_role": item["evaluator_role"], "rating": _rating_from_scores(item),
                 "rating_label": RATING_LABELS[_rating_from_scores(item)], "detail": item}
                for item in evaluation_details
            ]
            keyword = q.strip().casefold()
            if keyword:
                history = [item for item in history if keyword in " ".join(str(value or "") for value in (
                    item["title"], item["evaluator_name"], item["detail"].get("notes"),
                    item["detail"].get("comments"), item["detail"].get("strengths"),
                    item["detail"].get("improvements"),
                )).casefold()]
            if date_from:
                history = [item for item in history if item.get("date") and item["date"] >= date_from]
            if date_to:
                history = [item for item in history if item.get("date") and item["date"] <= date_to]
            if rating != "all":
                history = [item for item in history if item["rating"] == rating]
            history.sort(key=lambda item: str(item.get("date") or ""), reverse=True)
            history_total = len(history)
            history = history[(page - 1) * page_size:page * page_size]
            return {"employee_username": employee_username, "progress": progress,
                    "evaluations": evaluations, "evaluation_details": evaluation_details,
                    "history": history, "history_total": history_total, "page": page,
                    "page_size": page_size, "latest_radar": evaluations[-1] if evaluations else None}

    @app.get("/v2/training/evaluations/{assignment_id}/export.{file_format}")
    def export_evaluation(
        assignment_id: str,
        file_format: Literal["pdf", "png"],
        ident: identity_type = Depends(current_identity),
    ):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_view")
            row = conn.execute(text("""
                SELECT a.id,a.employee_username,a.evaluator_username,c.name cycle_name,c.end_date,
                       ev.craft_score,ev.communication_score,ev.attitude_score,ev.discipline_score,
                       ev.appearance_score,ev.hygiene_score,ev.attendance_score,
                       ev.strengths,ev.improvements,ev.comments
                FROM vera_evaluation_assignment a
                JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
                JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
                WHERE a.id=:id AND a.status='submitted'
            """), {"id": assignment_id}).mappings().first()
            if not row:
                raise HTTPException(404, "Không tìm thấy kết quả đánh giá đã hoàn thành.")
            item = dict(row)
            if not _is_admin(ident) and str(item["employee_username"]).lower() != ident.employee_username.lower():
                _require_assessment_pair(conn, ident.employee_username, str(item["employee_username"]))
        filename = f"VERA_DanhGia_{item['employee_username']}_{assignment_id[:8]}.{file_format}"
        if file_format == "png":
            content, media_type = _export_evaluation_png(item), "image/png"
        else:
            content, media_type = _export_evaluation_pdf(item), "application/pdf"
        return Response(content=content, media_type=media_type,
                        headers={"Content-Disposition": f'attachment; filename="{filename}"'})

    @app.put("/v2/training/notification-recipients")
    def save_notification_recipients(body: NotificationRecipientsInput, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_admin"); _require_admin(ident)
            conn.execute(text("UPDATE vera_training_notification_recipient SET active=FALSE,updated_at=NOW(),updated_by=:actor"), {"actor": ident.employee_username})
            for username in dict.fromkeys(item.strip() for item in body.usernames if item.strip()):
                employee = _employee(conn, username)
                if not employee or str(employee["employment_status"]).strip().lower() not in {"đang làm việc", "active"}:
                    raise HTTPException(400, f"Tài khoản nhận thông báo không hợp lệ: {username}")
                conn.execute(text("""
                    INSERT INTO vera_training_notification_recipient(username,active,updated_by)
                    VALUES (:username,TRUE,:actor)
                    ON CONFLICT (username) DO UPDATE SET active=TRUE,updated_by=EXCLUDED.updated_by,updated_at=NOW()
                """), {"username": username, "actor": ident.employee_username})
            _audit(conn, "training_notification_settings", "recipients", "replace", ident.employee_username,
                   {"usernames": body.usernames})
            return {"ok": True}

    @app.get("/v2/training/notifications")
    def training_notifications(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn)
            items = _rows(conn.execute(text("""
                SELECT id,title,body,reference_type,reference_id,is_read,created_at
                FROM vera_training_notification WHERE lower(recipient_username)=lower(:viewer)
                ORDER BY created_at DESC LIMIT 50
            """), {"viewer": ident.employee_username}))
            return {"notifications": items, "unread": sum(not item["is_read"] for item in items)}

    @app.post("/v2/training/notifications/{notification_id}/read")
    def read_training_notification(notification_id: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn)
            row = conn.execute(text("""
                UPDATE vera_training_notification SET is_read=TRUE,read_at=COALESCE(read_at,NOW())
                WHERE id=:id AND lower(recipient_username)=lower(:viewer)
                RETURNING reference_type,reference_id
            """), {"id": notification_id, "viewer": ident.employee_username}).mappings().first()
            if not row: raise HTTPException(404, "Không tìm thấy thông báo.")
            return {"ok": True, **dict(row)}

    @app.get("/v2/training/notifications/{notification_id}/detail")
    def training_notification_detail(notification_id: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn)
            notice = conn.execute(text("""
                SELECT * FROM vera_training_notification
                WHERE id=:id AND lower(recipient_username)=lower(:viewer)
            """), {"id": notification_id, "viewer": ident.employee_username}).mappings().first()
            if not notice: raise HTTPException(404, "Không tìm thấy thông báo.")
            if notice["reference_type"] == "daily_training":
                detail = conn.execute(text("""
                    SELECT ts.*,ts.employee_username employee_name,
                           ts.trainer_username evaluator_name
                    FROM vera_training_session ts
                    LEFT JOIN employees e ON lower(e.username)=lower(ts.employee_username)
                    LEFT JOIN employees t ON lower(t.username)=lower(ts.trainer_username)
                    WHERE ts.id=:id
                """), {"id": notice["reference_id"]}).mappings().first()
            elif notice["reference_type"] == "evaluation_cycle":
                detail = conn.execute(text("""
                    SELECT c.id,c.name cycle_name,c.start_date,c.end_date,c.status,
                           COUNT(DISTINCT a.employee_username)::int employee_count,
                           COUNT(DISTINCT a.evaluator_username)::int evaluator_count,
                           STRING_AGG(DISTINCT a.employee_username, ', ' ORDER BY a.employee_username) employee_name,
                           STRING_AGG(DISTINCT a.evaluator_username, ', ' ORDER BY a.evaluator_username) evaluator_name
                    FROM vera_evaluation_cycle c
                    JOIN vera_evaluation_assignment a ON a.cycle_id=c.id
                    WHERE c.id=:id GROUP BY c.id
                """), {"id": notice["reference_id"]}).mappings().first()
            else:
                detail = conn.execute(text("""
                    SELECT a.*,c.name cycle_name,c.end_date,
                           a.employee_username employee_name,
                           a.evaluator_username evaluator_name,ev.*
                    FROM vera_evaluation_assignment a JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
                    JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
                    LEFT JOIN employees e ON lower(e.username)=lower(a.employee_username)
                    LEFT JOIN employees t ON lower(t.username)=lower(a.evaluator_username)
                    WHERE a.id=:id
                """), {"id": notice["reference_id"]}).mappings().first()
            if not detail: raise HTTPException(404, "Nội dung đánh giá không còn tồn tại.")
            conn.execute(text("UPDATE vera_training_notification SET is_read=TRUE,read_at=COALESCE(read_at,NOW()) WHERE id=:id"), {"id": notification_id})
            return {"notification": dict(notice), "detail": dict(detail)}
