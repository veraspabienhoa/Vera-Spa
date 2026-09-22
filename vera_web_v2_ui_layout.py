"""Shared, versioned layout preferences. Admin writes; authenticated users read."""
import json
import re
from typing import Literal
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

class LayoutItem(BaseModel):
    order: int | None = Field(default=None, ge=0, le=10000)
    width: int | None = Field(default=None, ge=32, le=2400)
    height: int | None = Field(default=None, ge=24, le=1600)
    parent: str | None = Field(default=None, max_length=80)

class LayoutWrite(BaseModel):
    device: Literal['mobile', 'desktop']
    revision: int = Field(ge=0)
    items: dict[str, LayoutItem]


def validate_items(items):
    if len(items) > 2000 or any(not re.fullmatch(r'l-[a-z0-9-]{1,70}', key) for key in items):
        raise HTTPException(400, 'Bố cục không hợp lệ hoặc vượt quá 2.000 thành phần.')
    for item in items.values():
        if item.parent and not re.fullmatch(r'l-[a-z0-9-]{1,70}', item.parent):
            raise HTTPException(400, 'Nhóm bố cục không hợp lệ.')
    return {key: item.model_dump(exclude_none=True) for key, item in items.items()}


def read_layout(conn):
    row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='ui' AND setting_key='shared_layout'" )).mappings().first()
    return {'layout': row['value_json'] if row else {'desktop': {}, 'mobile': {}}, 'revision': int(row['revision']) if row else 0}


def install_ui_layout_routes(app, *, engine_instance, current_identity, identity_type):
    @app.get('/v2/ui-layout')
    def get_layout(ident: identity_type = Depends(current_identity)):
        with engine_instance().begin() as conn:
            return read_layout(conn)

    @app.put('/v2/ui-layout')
    def put_layout(body: LayoutWrite, ident: identity_type = Depends(current_identity)):
        if str(ident.role).lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được thay đổi bố cục dùng chung.')
        items = validate_items(body.items)
        with engine_instance().begin() as conn:
            conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:ui:shared-layout'))"))
            current = read_layout(conn)
            if current['revision'] != body.revision:
                raise HTTPException(409, 'Bố cục đã được Admin khác cập nhật. Hãy tải lại trước khi sửa.')
            layout = {**current['layout'], body.device: items}
            revision = current['revision'] + 1
            conn.execute(text("""INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
                VALUES ('ui','shared_layout',CAST(:value AS jsonb),'web_v2',:actor,:revision,NOW(),NOW())
                ON CONFLICT(category,setting_key) DO UPDATE SET value_json=EXCLUDED.value_json,
                updated_by=EXCLUDED.updated_by,revision=EXCLUDED.revision,updated_at=NOW()"""),
                {'value': json.dumps(layout), 'actor': ident.employee_username, 'revision': revision})
            return {'layout': layout, 'revision': revision}
