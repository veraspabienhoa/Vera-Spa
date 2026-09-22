"""Admin cleanup of filtered board snapshots, never current Live Tour/financial data."""
from datetime import date
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import text
from vera_live_tour_relational import BOARD_HISTORY_TABLE, ensure_schema

class HistoryFilter(BaseModel):
    date_from: date | None = None
    date_to: date | None = None
    employee: str = Field(default='', max_length=200)
    @model_validator(mode='after')
    def dates(self):
        if self.date_from and self.date_to and self.date_from > self.date_to:
            raise ValueError('Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.')
        return self

class HistoryDelete(HistoryFilter):
    cutoff_id: int = Field(ge=1)
    confirm: bool = False

WHERE = """(CAST(:date_from AS date) IS NULL OR (changed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date >= CAST(:date_from AS date))
 AND (CAST(:date_to AS date) IS NULL OR (changed_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date <= CAST(:date_to AS date))
 AND (:employee = '' OR employee_name ILIKE '%' || :employee || '%')"""


def install_board_history_cleanup(app, *, engine_instance, current_identity, identity_type):
    def admin(ident):
        if str(ident.role).lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được xóa lịch sử bảng tua.')

    @app.post('/v2/live-tour/board-history/cleanup-preview')
    def preview(body: HistoryFilter, ident: identity_type = Depends(current_identity)):
        admin(ident)
        params = body.model_dump(); params['employee'] = body.employee.strip()
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            row = conn.execute(text(f'SELECT COUNT(*) count, COALESCE(MAX(id),0) cutoff_id FROM {BOARD_HISTORY_TABLE} WHERE {WHERE}'), params).mappings().one()
            return dict(row)

    @app.delete('/v2/live-tour/board-history')
    def delete(body: HistoryDelete, ident: identity_type = Depends(current_identity)):
        admin(ident)
        if not body.confirm:
            raise HTTPException(400, 'Cần xác nhận trước khi xóa lịch sử.')
        params = body.model_dump(); params['employee'] = body.employee.strip()
        with engine_instance().begin() as conn:
            ensure_schema(conn)
            count = conn.execute(text(f'''WITH removed AS (
                DELETE FROM {BOARD_HISTORY_TABLE} WHERE {WHERE} AND id <= :cutoff_id RETURNING id
            ) SELECT COUNT(*) FROM removed'''), params).scalar_one()
        return {'ok': True, 'deleted': count}
