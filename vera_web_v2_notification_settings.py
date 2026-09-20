"""Central, admin-managed switches for every VERA notification family."""
from __future__ import annotations

from typing import Any, Callable

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text


RELEASE = "notification-settings-2026-09-20-v1"
CATALOG = (
    ("birthday", "Sinh nhật", "Nhắc sinh nhật nhân viên trong tháng.", "Quản lý, lễ tân", "Trong ứng dụng"),
    ("profile_completion", "Hoàn thiện hồ sơ", "Nhắc nhân viên bổ sung thông tin và ảnh CCCD còn thiếu.", "Nhân viên", "Trong ứng dụng, thiết bị"),
    ("leave_watch", "Theo dõi ngày nghỉ", "Thông báo khi danh sách đăng ký nghỉ ở ngày đang theo dõi thay đổi.", "Người theo dõi", "Trong ứng dụng"),
    ("admin_leave_changes", "Thay đổi đăng ký nghỉ", "Báo cho Admin khi có đăng ký, sửa hoặc xóa ngày nghỉ.", "Admin", "Thông báo đẩy"),
    ("auto_penalty", "Phạt tự động", "Thông báo khi hệ thống tự động ghi nhận một khoản phạt.", "Nhân viên, quản lý", "Thông báo đẩy"),
    ("missing_checkin", "Thiếu chấm công FaceID", "Cảnh báo nhân viên có lịch làm nhưng chưa chấm công đúng hạn.", "Nhân viên, lễ tân, quản lý", "Thông báo đẩy"),
    ("attendance_break", "Nghỉ giữa ca", "Cảnh báo đến giờ nghỉ, sắp hết giờ hoặc quá giờ nghỉ giữa ca.", "Nhân viên, lễ tân, quản lý", "Trong ứng dụng, thông báo đẩy"),
    ("live_tour_queue", "Hàng đợi Live Tour", "Cảnh báo hàng đợi đồng bộ Live Tour lỗi, quá tải hoặc đã phục hồi.", "Admin", "Thông báo đẩy"),
    ("purchase_reconcile", "Đối chiếu mua hàng", "Cảnh báo khi số liệu mua hàng và Doanh thu-Chi phí không khớp.", "Admin, quản lý", "Thông báo đẩy"),
)
VALID_KEYS = frozenset(row[0] for row in CATALOG)


class NotificationSettingUpdate(BaseModel):
    enabled: bool


def ensure_schema(conn) -> None:
    conn.execute(text("""
        CREATE TABLE IF NOT EXISTS vera_v2_notification_setting (
          notification_key TEXT PRIMARY KEY,
          enabled BOOLEAN NOT NULL DEFAULT TRUE,
          updated_by TEXT NOT NULL DEFAULT '',
          updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
    """))


def is_enabled(conn, notification_key: str) -> bool:
    """Unknown and not-yet-configured notifications remain enabled."""
    if notification_key not in VALID_KEYS:
        return True
    ensure_schema(conn)
    value = conn.execute(text("""
        SELECT enabled FROM vera_v2_notification_setting
        WHERE notification_key=:notification_key
    """), {"notification_key": notification_key}).scalar_one_or_none()
    return True if value is None else bool(value)


def _settings(conn) -> list[dict[str, Any]]:
    ensure_schema(conn)
    saved = {
        str(row["notification_key"]): dict(row)
        for row in conn.execute(text("""
            SELECT notification_key,enabled,updated_by,updated_at
            FROM vera_v2_notification_setting
        """)).mappings()
    }
    output = []
    for key, label, description, audience, channel in CATALOG:
        row = saved.get(key, {})
        output.append({
            "key": key, "label": label, "description": description,
            "audience": audience, "channel": channel,
            "enabled": bool(row.get("enabled", True)),
            "updated_by": row.get("updated_by", ""),
            "updated_at": row.get("updated_at"),
        })
    return output


def install_notification_settings_routes(
    app, *, engine_instance: Callable[[], Any], current_identity, identity_type,
) -> None:
    if getattr(app.state, "notification_settings_installed", False):
        return

    @app.get("/v2/notification-settings")
    def get_notification_settings(_ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            return {"settings": _settings(conn), "release": RELEASE}

    @app.put("/v2/notification-settings/{notification_key}")
    def update_notification_setting(
        notification_key: str,
        body: NotificationSettingUpdate,
        ident: identity_type = Depends(current_identity),
    ):
        if str(getattr(ident, "role", "") or "").strip().lower() != "admin":
            raise HTTPException(403, "Chỉ Admin được thay đổi cấu hình thông báo.")
        if notification_key not in VALID_KEYS:
            raise HTTPException(404, "Không tìm thấy loại thông báo.")
        actor = str(getattr(ident, "employee_username", "") or getattr(ident, "email", "") or "admin")
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            conn.execute(text("""
                INSERT INTO vera_v2_notification_setting(notification_key,enabled,updated_by,updated_at)
                VALUES (:notification_key,:enabled,:updated_by,NOW())
                ON CONFLICT (notification_key) DO UPDATE SET
                  enabled=EXCLUDED.enabled,updated_by=EXCLUDED.updated_by,updated_at=NOW()
            """), {"notification_key": notification_key, "enabled": body.enabled, "updated_by": actor})
            item = next(row for row in _settings(conn) if row["key"] == notification_key)
        return {"ok": True, "setting": item}

    app.state.notification_settings_installed = True
    app.state.notification_settings_release = RELEASE
