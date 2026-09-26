"""Admin-only, transactionally read-only FaceGate attendance rehearsal."""
from datetime import date
from fastapi import Depends, HTTPException
from sqlalchemy import text

from vera_facegate_attendance import EvidenceError, preview


def install_facegate_attendance_routes(app, *, engine_instance, current_identity, identity_type):
    @app.get('/v2/devices/facegate-attendance/preview')
    def preview_attendance(start: date, end: date, ident: identity_type = Depends(current_identity)):
        if str(getattr(ident, 'role', '') or '').lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được đối chiếu chuyển nguồn chấm công.')
        if end < start or (end - start).days > 6:
            raise HTTPException(400, 'Chọn từ 1 đến 7 ngày để đối chiếu.')
        try:
            with engine_instance().begin() as conn:
                # The two projections and the mapping revision see one database
                # snapshot. Even an accidentally added write fails and rolls back.
                conn.execute(text('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY'))
                conn.execute(text("SET LOCAL statement_timeout='8s'"))
                return preview(conn, start, end)
        except EvidenceError as exc:
            raise HTTPException(409, {'message': 'Chưa thể đối chiếu đầy đủ dữ liệu đã lưu.', 'reason': str(exc)}) from exc
        except RuntimeError as exc:
            raise HTTPException(409, 'Cần khôi phục hồ sơ máy FaceGate trong Quản lý thiết bị trước khi đối chiếu.') from exc
