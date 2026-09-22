"""Central, admin-managed switches for every VERA notification family."""
from __future__ import annotations

from typing import Any, Callable, Literal
import json
import uuid
from pydantic import Field, field_validator
from vera_notification_delivery import ensure_schema as ensure_routing_schema
from vera_notification_tasks import task_catalog, TaskNotificationMiddleware

from fastapi import Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text


RELEASE = "notification-routing-2026-09-22-v2"
CATALOG = (
    ("training_completed", "Hoàn thành đào tạo / đánh giá", "Thông báo khi nhật ký đào tạo hoặc đánh giá hoàn tất.", "Admin, người được đánh giá và người đã cấu hình", "Trong ứng dụng"),
    ("training_cycle", "Đợt đánh giá mới", "Thông báo phân công đợt đánh giá nhân viên mới.", "Nhân viên và người đánh giá", "Trong ứng dụng"),
    ("leave_quota_exceeded", "Vượt hạn mức đăng ký nghỉ", "Cảnh báo vượt 5 ngày, 2 lần cuối tuần Nhóm 3 hoặc 2 lần phát sinh trong tháng.", "Admin", "Thông báo đẩy"),
    ("birthday", "Sinh nhật", "Nhắc sinh nhật nhân viên trong tháng.", "Quản lý, lễ tân", "Trong ứng dụng"),
    ("profile_completion", "Hoàn thiện hồ sơ", "Nhắc nhân viên bổ sung thông tin và ảnh CCCD còn thiếu.", "Nhân viên", "Trong ứng dụng, thiết bị"),
    ("leave_watch", "Theo dõi ngày nghỉ", "Thông báo khi danh sách đăng ký nghỉ ở ngày đang theo dõi thay đổi.", "Người theo dõi", "Trong ứng dụng"),
    ("admin_leave_changes", "Thay đổi đăng ký nghỉ", "Báo cho Admin khi có đăng ký, sửa hoặc xóa ngày nghỉ.", "Admin", "Thông báo đẩy"),
    ("long_leave_requests", "Đơn Phép năm / Làm đẹp / Nghỉ việc", "Báo ngay cho Admin khi nhân viên gửi một trong ba loại đơn.", "Admin", "Thông báo đẩy"),
    ("admin_daily_summary", "Báo cáo thay đổi hằng ngày", "Tổng hợp các thay đổi của hệ thống trong 24 giờ gửi cho Admin.", "Admin", "Thông báo đẩy"),
    ("auto_penalty", "Phạt tự động", "Thông báo khi hệ thống tự động ghi nhận một khoản phạt.", "Nhân viên, quản lý", "Thông báo đẩy"),
    ("missing_checkin", "Thiếu chấm công FaceID", "Cảnh báo nhân viên có lịch làm nhưng chưa chấm công đúng hạn.", "Nhân viên, lễ tân, quản lý", "Thông báo đẩy"),
    ("attendance_break", "Nghỉ giữa ca", "Cảnh báo đến giờ nghỉ, sắp hết giờ hoặc quá giờ nghỉ giữa ca.", "Nhân viên, lễ tân, quản lý", "Trong ứng dụng, thông báo đẩy"),
    ("live_tour_queue", "Hàng đợi Live Tour", "Cảnh báo hàng đợi đồng bộ Live Tour lỗi, quá tải hoặc đã phục hồi.", "Admin", "Thông báo đẩy"),
    ("purchase_reconcile", "Đối chiếu mua hàng", "Cảnh báo khi số liệu mua hàng và Doanh thu-Chi phí không khớp.", "Admin, quản lý", "Thông báo đẩy"),
    ("revenue_manual_changes", "Thay đổi Thu Chi thủ công", "Báo ngay cho Admin khi có dữ liệu Thu Chi thủ công mới, bị sửa hoặc bị xóa.", "Admin", "Thông báo đẩy"),
    ("ui_guidance", "Hướng dẫn chọn và bộ lọc", "Nhắc chọn nhân viên phù hợp, chọn dữ liệu, điều kiện tìm kiếm hoặc bộ lọc.", "Tất cả tài khoản", "Popup trong ứng dụng"),
    ("ui_success", "Thao tác thành công", "Xác nhận lưu, cập nhật, xuất file hoặc thao tác đã hoàn tất.", "Tất cả tài khoản", "Popup trong ứng dụng"),
    ("ui_warning", "Cảnh báo giao diện", "Các cảnh báo nghiệp vụ và trạng thái cần người dùng chú ý.", "Tất cả tài khoản", "Popup trong ứng dụng"),
    ("ui_error", "Lỗi hệ thống và kết nối", "Lỗi tải dữ liệu, lỗi máy chủ và mã HTTP như 500/502/503.", "Tất cả tài khoản", "Popup trong ứng dụng"),
)
VALID_KEYS = frozenset(row[0] for row in CATALOG)


class NotificationSettingUpdate(BaseModel):
    enabled: bool
    revision: int | None = Field(default=None, ge=0)
    recipients: list[str] | None = Field(default=None, max_length=200)
    channels: list[Literal['in_app', 'push']] | None = None
    reset_routing: bool = False

class NotificationCreate(BaseModel):
    label: str = Field(min_length=1, max_length=120)
    @field_validator('label')
    @classmethod
    def label_text(cls, value):
        if not value.strip(): raise ValueError('Nhập tên thông báo.')
        return value.strip()
    source_key: str = Field(min_length=1, max_length=160)
    recipients: list[str] = Field(min_length=1, max_length=200)
    channels: list[Literal['in_app','push']] = Field(min_length=1, max_length=2)
    revision: int = Field(ge=0)

class NotificationOrder(BaseModel):
    keys: list[str] = Field(max_length=1000)
    revision: int = Field(ge=0)


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


def _admin(ident):
    if getattr(ident, 'must_change_password', False): raise HTTPException(428, 'Hãy đổi mật khẩu trước khi thay đổi cấu hình.')
    if str(getattr(ident, 'role', '')).strip().lower() != 'admin':
        raise HTTPException(403, 'Chỉ Admin được thay đổi cấu hình thông báo.')


def _lock_config(conn, expected=None):
    ensure_schema(conn)
    ensure_routing_schema(conn)
    row = dict(conn.execute(text('SELECT revision,ordering FROM vera_notification_config WHERE id=1 FOR UPDATE')).mappings().one())
    if expected is not None and row['revision'] != expected:
        raise HTTPException(409, 'Cấu hình đã thay đổi. Hãy tải lại trước khi lưu.')
    return row


def _recipients(conn, values):
    if not values:
        raise HTTPException(400, 'Chọn ít nhất một người nhận.')
    wanted = sorted(set(values))
    active = {str(row['id']) for row in conn.execute(text('SELECT auth_user_id::text AS id FROM vera_v2_user_profile WHERE is_active')).mappings()}
    if any(value not in active for value in wanted):
        raise HTTPException(400, 'Người nhận không tồn tại hoặc tài khoản đã bị khóa.')
    return wanted


def _write_route(conn, key, source, label, recipients, channels, custom, actor):
    recipients = _recipients(conn, recipients)
    if not channels:
        raise HTTPException(400, 'Chọn ít nhất một kênh thông báo.')
    conn.execute(text("""INSERT INTO vera_notification_route(key,source_key,label,recipients,channels,custom,updated_by)
        VALUES(:key,:source,:label,CAST(:recipients AS jsonb),CAST(:channels AS jsonb),:custom,:actor)
        ON CONFLICT(key) DO UPDATE SET recipients=EXCLUDED.recipients,channels=EXCLUDED.channels,
        updated_by=EXCLUDED.updated_by,updated_at=NOW()"""),
        {'key':key,'source':source,'label':label,'recipients':json.dumps(recipients),'channels':json.dumps(sorted(set(channels))), 'custom':custom,'actor':actor})


def _response(conn, admin=False):
    ensure_schema(conn); ensure_routing_schema(conn)
    routes = {row['key']: dict(row) for row in conn.execute(text('SELECT * FROM vera_notification_route ORDER BY updated_at,key')).mappings()}
    items = _settings(conn)
    states = {row['notification_key']: row['enabled'] for row in conn.execute(text('SELECT notification_key,enabled FROM vera_v2_notification_setting')).mappings()}
    for route in routes.values():
        if route['custom']:
            items.append({'key':route['key'],'label':route['label'],'description':'Thông báo theo tác vụ đã chọn.',
                'audience':'Tùy chỉnh','channel':'Tùy chỉnh','enabled':states.get(route['key'],True),'custom':True})
    config = dict(conn.execute(text('SELECT revision,ordering FROM vera_notification_config WHERE id=1')).mappings().one())
    order = {key:index for index,key in enumerate(config['ordering'])}
    for item in items:
        route = routes.get(item['key'])
        item['routed'] = bool(route)
        item['has_rules'] = any(row['source_key']==item['key'] for row in routes.values())
        if admin:
            item.update(recipients=route['recipients'] if route else [], channels=route['channels'] if route else [], source_key=route['source_key'] if route else item['key'])
    items.sort(key=lambda item: order.get(item['key'],10000))
    response = {'settings':items,'release':RELEASE,'revision':config['revision']}
    if admin:
        response['recipients'] = [dict(row) for row in conn.execute(text("""SELECT p.auth_user_id::text AS id,
            p.employee_username AS username,COALESCE(e.full_name,p.employee_username) AS name,p.role
            FROM vera_v2_user_profile p LEFT JOIN employees e ON e.username=p.employee_username
            WHERE p.is_active ORDER BY e.full_name,p.employee_username""")).mappings()]
        response['channels'] = [{'key':'in_app','label':'Trong ứng dụng'},{'key':'push','label':'Thông báo đẩy trên thiết bị'}]
    return response


def install_notification_settings_routes(app, *, engine_instance, current_identity, identity_type, api_module=None):
    if getattr(app.state, 'notification_settings_installed', False): return
    globals()['identity_type'] = identity_type

    @app.get('/v2/notification-settings')
    def get_settings(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            return _response(conn, str(getattr(ident,'role','')).lower()=='admin')

    @app.get('/v2/notification-settings/tasks')
    def get_tasks(ident: identity_type = Depends(current_identity)):
        _admin(ident)
        return {'tasks': [{'key':r[0],'label':r[1],'description':r[2],'group':'Thông báo hiện có'} for r in CATALOG] + task_catalog(app)}

    @app.put('/v2/notification-settings/order')
    def save_order(body: NotificationOrder, ident: identity_type = Depends(current_identity)):
        _admin(ident)
        with engine_instance().begin() as conn:
            _lock_config(conn, body.revision)
            valid = {item['key'] for item in _response(conn)['settings']}
            if len(body.keys)!=len(set(body.keys)) or set(body.keys)!=valid:
                raise HTTPException(400,'Danh sách thứ tự không khớp cấu hình hiện tại.')
            conn.execute(text('UPDATE vera_notification_config SET ordering=CAST(:keys AS jsonb),revision=revision+1 WHERE id=1'), {'keys':json.dumps(body.keys)})
            return _response(conn,True)

    @app.post('/v2/notification-settings')
    def create_notification(body: NotificationCreate, ident: identity_type = Depends(current_identity)):
        _admin(ident)
        if body.source_key not in VALID_KEYS | {item['key'] for item in task_catalog(app)}:
            raise HTTPException(400,'Tác vụ chưa được hệ thống hỗ trợ.')
        with engine_instance().begin() as conn:
            _lock_config(conn,body.revision)
            if len(_response(conn)['settings']) >= 1000: raise HTTPException(400,'Đã đạt giới hạn 1.000 thông báo.')
            key='custom-'+uuid.uuid4().hex
            _write_route(conn,key,body.source_key,body.label.strip(),body.recipients,body.channels,True,ident.employee_username)
            conn.execute(text('UPDATE vera_notification_config SET revision=revision+1 WHERE id=1'))
            return _response(conn,True)

    @app.put('/v2/notification-settings/{notification_key}')
    def update_setting(notification_key: str, body: NotificationSettingUpdate, ident: identity_type = Depends(current_identity)):
        _admin(ident)
        with engine_instance().begin() as conn:
            _lock_config(conn,body.revision)
            item=next((item for item in _response(conn,True)['settings'] if item['key']==notification_key),None)
            if not item: raise HTTPException(404,'Không tìm thấy loại thông báo.')
            if body.reset_routing:
                if item.get('custom'): raise HTTPException(400,'Thông báo tự tạo cần người nhận và kênh gửi.')
                conn.execute(text('DELETE FROM vera_notification_route WHERE key=:key'),{'key':notification_key})
            elif body.recipients is not None or body.channels is not None:
                _write_route(conn,notification_key,item['source_key'],item['label'],body.recipients,body.channels,item.get('custom',False),ident.employee_username)
            conn.execute(text("""INSERT INTO vera_v2_notification_setting(notification_key,enabled,updated_by)
                VALUES(:key,:enabled,:actor) ON CONFLICT(notification_key) DO UPDATE SET
                enabled=EXCLUDED.enabled,updated_by=EXCLUDED.updated_by,updated_at=NOW()"""),
                {'key':notification_key,'enabled':body.enabled,'actor':ident.employee_username})
            conn.execute(text('UPDATE vera_notification_config SET revision=revision+1 WHERE id=1'))
            result=_response(conn,True)
            return {**result,'ok':True,'setting':next(i for i in result['settings'] if i['key']==notification_key)}

    @app.post('/v2/notification-local/{notification_key}')
    def local_event(notification_key: str, ident: identity_type = Depends(current_identity)):
        # Browser-origin notices use fixed server text, never accept arbitrary alert content.
        if notification_key not in {'birthday','profile_completion','ui_guidance','ui_success','ui_warning','ui_error'}:
            raise HTTPException(400,'Loại sự kiện trình duyệt không hợp lệ.')
        from datetime import datetime, timezone
        from vera_notification_delivery import enqueue
        label=next(row[1] for row in CATALOG if row[0]==notification_key)
        now=datetime.now(timezone.utc)
        bucket=now.strftime('%Y%m%d') if notification_key in {'birthday','profile_completion'} else now.strftime('%Y%m%d%H%M')
        event=f"local:{notification_key}:{ident.auth_user_id}:{bucket}"
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            if is_enabled(conn,notification_key):
                enqueue(conn,notification_key,{'title':f'VERA SPA · {label}',
                    'body':f"{ident.full_name or ident.employee_username} nhận thông báo {label.lower()} trên ứng dụng."},event)
        return {'ok':True}

    @app.get('/v2/notification-inbox')
    def inbox(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            ensure_schema(conn); ensure_routing_schema(conn)
            rows=conn.execute(text("""SELECT d.id,d.payload,d.created_at,d.read_at FROM vera_notification_delivery d
                JOIN vera_notification_route r ON r.key=d.rule_key
                LEFT JOIN vera_v2_notification_setting s ON s.notification_key=r.key
                WHERE d.recipient=:recipient AND d.channel='in_app' AND r.recipients ? :recipient
                AND r.channels ? 'in_app' AND COALESCE(s.enabled,TRUE)
                ORDER BY d.id DESC LIMIT 100"""),{'recipient':str(ident.auth_user_id)}).mappings()
            return {'notifications':[dict(row) for row in rows]}

    @app.post('/v2/notification-inbox/{notification_id}/read')
    def mark_read(notification_id: int, ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            conn.execute(text('UPDATE vera_notification_delivery SET read_at=NOW() WHERE id=:id AND recipient=:recipient'),
                {'id':notification_id,'recipient':str(ident.auth_user_id)})
        return {'ok':True}

    app.add_middleware(TaskNotificationMiddleware, owner=app, engine_instance=engine_instance)
    if api_module is not None:
        from threading import Event, Thread
        from contextlib import asynccontextmanager
        from vera_notification_delivery import dispatch_pending
        original_lifespan=app.router.lifespan_context
        @asynccontextmanager
        async def lifespan(application):
            stop=Event()
            def work():
                while not stop.wait(15):
                    try: dispatch_pending(engine_instance(),api_module._send_web_push,api_module._vault_secret)
                    except Exception: pass
            async with original_lifespan(application):
                thread=Thread(target=work,name='vera-notification-delivery',daemon=True);thread.start()
                try: yield
                finally: stop.set();thread.join(timeout=2)
        app.router.lifespan_context=lifespan
    app.state.notification_settings_installed=True
    app.state.notification_settings_release=RELEASE
