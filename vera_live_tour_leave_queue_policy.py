"""Admin-controlled reason list for the once-daily Live Tour queue batch."""
import json

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

CATEGORY = 'leave_rules'
SETTING_KEY = 'live_tour_leave_queue_0300'
REASONS = (
    'Về sớm CÓ phép', 'Về sớm KHÔNG phép', 'Về sớm CUỐI TUẦN CÓ phép',
    'Về sớm CUỐI TUẦN KHÔNG phép', 'Về sớm phát sinh',
    'Leader về sớm về sớm theo chính sách',
    'Về sớm bệnh có giấy khám hoặc được quản lý duyệt',
    'Nghỉ KHÔNG phép', 'Nghỉ CUỐI TUẦN KHÔNG phép',
)


class PolicyUpdate(BaseModel):
    enabled: bool
    reasons: list[str] = Field(max_length=9)
    expected_revision: int = Field(ge=0)


def load_policy(conn):
    row = conn.execute(text('SELECT value_json, revision FROM vera_app_setting WHERE category=:category AND setting_key=:key'),
                       {'category': CATEGORY, 'key': SETTING_KEY}).mappings().first()
    value = row['value_json'] if row else {'enabled': True, 'reasons': list(REASONS)}
    return {'enabled': value.get('enabled') is True,
            'reasons': [reason for reason in REASONS if reason in value.get('reasons', [])],
            'available_reasons': list(REASONS), 'revision': int(row['revision'] or 0) if row else 0}


def install_routes(app, *, engine_instance, current_identity, require_feature, identity_type):
    @app.put('/v2/rules/live-tour-leave-queue')
    def save_policy(body: PolicyUpdate, ident: identity_type = Depends(current_identity)):
        if str(getattr(ident, 'role', '')).strip().lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được thay đổi nội quy xếp cuối bảng tua.')
        if len(set(body.reasons)) != len(body.reasons) or any(reason not in REASONS for reason in body.reasons):
            raise HTTPException(422, 'Danh sách lý do không hợp lệ.')
        with engine_instance().begin() as conn:
            require_feature(conn, ident, 'official_rules_edit')
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:leave-queue-policy'))"))
            current = load_policy(conn)
            if current['revision'] != body.expected_revision:
                raise HTTPException(409, 'Nội quy đã thay đổi. Hãy làm mới trước khi lưu lại.')
            value = {'enabled': body.enabled, 'reasons': [reason for reason in REASONS if reason in body.reasons]}
            conn.execute(text('''
                INSERT INTO vera_app_setting(category, setting_key, value_json, revision, source, updated_by, created_at, updated_at)
                VALUES(:category,:key,CAST(:value AS jsonb),1,'web_v2_rules',:actor,NOW(),NOW())
                ON CONFLICT(category,setting_key) DO UPDATE SET
                    value_json=EXCLUDED.value_json, revision=vera_app_setting.revision+1,
                    source=EXCLUDED.source, updated_by=EXCLUDED.updated_by, updated_at=NOW()
            '''), {'category': CATEGORY, 'key': SETTING_KEY, 'value': json.dumps(value, ensure_ascii=False),
                   'actor': ident.employee_username})
            return {**load_policy(conn), 'message': 'Đã lưu. Áp dụng tại lượt xếp tua 03:00 kế tiếp.'}
