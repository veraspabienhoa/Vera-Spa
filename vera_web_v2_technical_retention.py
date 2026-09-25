"""Admin control over the retention of completed technical queue jobs."""
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_technical_retention import SETTING_TABLE, MAX_INTERVAL_HOURS, ensure_setting, public_setting


class RetentionUpdate(BaseModel):
    days: int = Field(ge=1, le=3)
    cleanup_interval_hours: int | None = Field(default=None, ge=1, le=MAX_INTERVAL_HOURS, strict=True)


def install_technical_retention_routes(app, *, engine_instance, current_identity):
    def admin(ident):
        if str(getattr(ident, 'role', '') or '').strip().lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được cài đặt thời gian lưu nhật ký kỹ thuật.')

    @app.get('/v2/settings/technical-retention')
    def get_retention(ident=Depends(current_identity)):
        admin(ident)
        with engine_instance().begin() as conn:
            ensure_setting(conn)
            return public_setting(conn)

    @app.put('/v2/settings/technical-retention')
    def put_retention(body: RetentionUpdate, ident=Depends(current_identity)):
        admin(ident)
        with engine_instance().begin() as conn:
            ensure_setting(conn)
            conn.execute(text(f'''UPDATE {SETTING_TABLE}
                SET retention_days=:days,
                    cleanup_interval_hours=COALESCE(:hours,cleanup_interval_hours),
                    updated_at=NOW(),updated_by=:actor WHERE singleton=1'''),
                {'days': body.days, 'hours': body.cleanup_interval_hours,
                 'actor': str(getattr(ident, 'employee_username', '') or getattr(ident, 'email', '') or 'admin')})
            return public_setting(conn)
