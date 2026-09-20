"""Training sessions, periodic employee evaluations, and analytics for Web V2."""
from __future__ import annotations

from datetime import date, time
from typing import Any, Callable, Literal
from uuid import uuid4

from fastapi import Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import text


GRADE_SCORE = {"E": 1, "D": 2, "C": 3, "B": 4, "A": 5, "A+": 6}


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
        CREATE INDEX IF NOT EXISTS idx_training_session_employee_date
            ON vera_training_session(employee_username, training_date DESC);
        CREATE INDEX IF NOT EXISTS idx_training_assignment_evaluator
            ON vera_evaluation_assignment(evaluator_username, status);
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


def _audit(conn, entity_type: str, entity_id: str, action: str, actor: str, detail: dict | None = None) -> None:
    conn.execute(text("""
        INSERT INTO vera_training_audit(entity_type, entity_id, action, actor_username, detail)
        VALUES (:entity_type, :entity_id, :action, :actor, CAST(:detail AS jsonb))
    """), {"entity_type": entity_type, "entity_id": entity_id, "action": action,
             "actor": actor, "detail": __import__("json").dumps(detail or {}, ensure_ascii=False)})


def install_training_routes(
    app, *, engine_instance: Callable[[], Any], current_identity: Callable,
    require_feature: Callable, identity_type: Any,
) -> None:
    @app.get("/v2/training/bootstrap")
    def training_bootstrap(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn)
            require_feature(conn, ident, "training_view")
            employee_filter = "" if _is_admin(ident) else """
                AND EXISTS (SELECT 1 FROM vera_training_scope s WHERE s.active=TRUE
                    AND lower(s.trainer_username)=lower(:viewer)
                    AND lower(s.employee_username)=lower(e.username))
            """
            employees = _rows(conn.execute(text("""
                SELECT e.username, COALESCE(NULLIF(e.full_name,''), e.username) AS full_name,
                       COALESCE(e.role,'') AS role
                FROM employees e
                WHERE COALESCE(e.payload->>'__deleted','false') <> 'true'
            """ + employee_filter + " ORDER BY lower(COALESCE(NULLIF(e.full_name,''), e.username))"),
                {"viewer": ident.employee_username}))
            sessions_filter = "" if _is_admin(ident) else """
                WHERE EXISTS (SELECT 1 FROM vera_training_scope s WHERE s.active=TRUE
                    AND lower(s.trainer_username)=lower(:viewer)
                    AND lower(s.employee_username)=lower(ts.employee_username))
            """
            sessions = _rows(conn.execute(text("""
                SELECT ts.*, COALESCE(NULLIF(e.full_name,''), ts.employee_username) employee_name,
                       COALESCE(NULLIF(t.full_name,''), ts.trainer_username) trainer_name
                FROM vera_training_session ts
                LEFT JOIN employees e ON lower(e.username)=lower(ts.employee_username)
                LEFT JOIN employees t ON lower(t.username)=lower(ts.trainer_username)
            """ + sessions_filter + " ORDER BY ts.training_date DESC, ts.start_time DESC LIMIT 300"),
                {"viewer": ident.employee_username}))
            assignments = _rows(conn.execute(text("""
                SELECT a.*, c.name cycle_name, c.start_date, c.end_date, c.status cycle_status,
                       COALESCE(NULLIF(e.full_name,''), a.employee_username) employee_name,
                       ev.craft_score, ev.communication_score, ev.attitude_score,
                       ev.discipline_score, ev.appearance_score, ev.hygiene_score,
                       ev.attendance_score, ev.strengths, ev.improvements, ev.comments
                FROM vera_evaluation_assignment a
                JOIN vera_evaluation_cycle c ON c.id=a.cycle_id
                LEFT JOIN employees e ON lower(e.username)=lower(a.employee_username)
                LEFT JOIN vera_employee_evaluation ev ON ev.assignment_id=a.id
                WHERE (:admin OR lower(a.evaluator_username)=lower(:viewer))
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
                SELECT s.*, COALESCE(NULLIF(t.full_name,''),s.trainer_username) trainer_name,
                       COALESCE(NULLIF(e.full_name,''),s.employee_username) employee_name
                FROM vera_training_scope s
                LEFT JOIN employees t ON lower(t.username)=lower(s.trainer_username)
                LEFT JOIN employees e ON lower(e.username)=lower(s.employee_username)
                WHERE s.active=TRUE ORDER BY trainer_name, employee_name
            """))) if _is_admin(ident) else []
            people = _rows(conn.execute(text("""
                SELECT username, COALESCE(NULLIF(full_name,''),username) full_name, COALESCE(role,'') role
                FROM employees WHERE COALESCE(payload->>'__deleted','false') <> 'true'
                ORDER BY lower(COALESCE(NULLIF(full_name,''),username))
            """))) if _is_admin(ident) else employees
            return {"employees": employees, "people": people, "sessions": sessions,
                    "assignments": assignments, "cycles": cycles, "scopes": scopes,
                    "is_admin": _is_admin(ident)}

    @app.post("/v2/training/sessions")
    def create_training_session(body: TrainingSessionInput, ident: identity_type = Depends(current_identity)):
        if body.end_time <= body.start_time:
            raise HTTPException(400, "Giờ kết thúc phải sau giờ bắt đầu.")
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_session_create")
            if not _scope_allowed(conn, ident, body.employee_username):
                raise HTTPException(403, "Nhân viên không thuộc phạm vi được phân công.")
            session_id = str(uuid4())
            params = body.model_dump(); params.update({"id": session_id, "trainer": ident.employee_username})
            conn.execute(text("""
                INSERT INTO vera_training_session(
                    id, employee_username, trainer_username, training_date, start_time, end_time,
                    topic, learning_attitude, skill_grade, strengths, improvements, notes, updated_by)
                VALUES (:id,:employee_username,:trainer,:training_date,:start_time,:end_time,
                    :topic,:learning_attitude,:skill_grade,:strengths,:improvements,:notes,:trainer)
            """), params)
            _audit(conn, "training_session", session_id, "create", ident.employee_username)
            return {"ok": True, "id": session_id}

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
            if not _scope_allowed(conn, ident, body.employee_username):
                raise HTTPException(403, "Nhân viên không thuộc phạm vi được phân công.")
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
            for employee in dict.fromkeys(body.employee_usernames):
                for evaluator in dict.fromkeys(body.evaluator_usernames):
                    evaluator_role = conn.execute(text("SELECT lower(COALESCE(role,'')) FROM employees WHERE lower(username)=lower(:username)"), {"username": evaluator}).scalar_one_or_none()
                    if evaluator_role != "admin" and not conn.execute(text("""
                        SELECT 1 FROM vera_training_scope WHERE active=TRUE
                        AND lower(trainer_username)=lower(:trainer)
                        AND lower(employee_username)=lower(:employee)
                    """), {"trainer": evaluator, "employee": employee}).scalar_one_or_none():
                        raise HTTPException(400, f"{evaluator} chưa được phân công quản lý {employee}.")
                    conn.execute(text("""
                        INSERT INTO vera_evaluation_assignment(id,cycle_id,employee_username,evaluator_username)
                        VALUES (:id,:cycle,:employee,:evaluator)
                    """), {"id": str(uuid4()), "cycle": cycle_id, "employee": employee, "evaluator": evaluator})
            _audit(conn, "evaluation_cycle", cycle_id, "create", ident.employee_username)
            return {"ok": True, "id": cycle_id}

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
            if not _scope_allowed(conn, ident, str(assignment["employee_username"])):
                raise HTTPException(403, "Nhân viên không thuộc phạm vi được phân công.")
            if assignment["cycle_status"] != "active":
                raise HTTPException(409, "Đợt đánh giá chưa kích hoạt hoặc đã đóng.")
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
            _audit(conn, "evaluation", assignment_id, "submit" if body.submit else "save_draft", ident.employee_username)
            return {"ok": True}

    @app.get("/v2/training/reports/{employee_username}")
    def employee_training_report(employee_username: str, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            _schema(conn); require_feature(conn, ident, "training_view")
            if not _scope_allowed(conn, ident, employee_username):
                raise HTTPException(403, "Nhân viên không thuộc phạm vi được phân công.")
            progress = _rows(conn.execute(text("""
                SELECT id, training_date, topic, skill_grade, learning_attitude, trainer_username,
                       strengths, improvements, notes
                FROM vera_training_session WHERE lower(employee_username)=lower(:employee)
                ORDER BY training_date, start_time
            """), {"employee": employee_username}))
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
                WHERE lower(a.employee_username)=lower(:employee) AND a.status='submitted'
                GROUP BY c.id, c.name, c.end_date ORDER BY c.end_date
            """), {"employee": employee_username}))
            return {"employee_username": employee_username, "progress": progress,
                    "evaluations": evaluations, "latest_radar": evaluations[-1] if evaluations else None}
