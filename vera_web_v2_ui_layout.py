"""Shared, versioned layout preferences. Admin writes; authenticated users read."""
import json
import re
from typing import Literal
from pathlib import Path
from pydantic import field_validator
REGISTRY = json.loads(Path(__file__).with_name("vera_ui_registry.json").read_text())
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

class LayoutItem(BaseModel):
    order: int | None = Field(default=None, ge=0, le=10000)
    width: int | None = Field(default=None, ge=32, le=2400)
    height: int | None = Field(default=None, ge=24, le=1600)
    text_align: Literal['left', 'center', 'right', 'justify'] | None = None
    content_align: Literal['start', 'center', 'end'] | None = None
    justify_content: Literal['start', 'center', 'end', 'space-between', 'space-around', 'space-evenly'] | None = None
    align_items: Literal['start', 'center', 'end', 'stretch'] | None = None
    gap: int | None = Field(default=None, ge=0, le=100)
    parent: str | None = Field(default=None, max_length=80)
    label: str | None = Field(default=None, max_length=100)
    mode: Literal['fit', 'group'] | None = None
    rows: Literal[0, 1, 2, 3, 4] | None = None
    font_size: int | None = Field(default=None, ge=12, le=24)

    @field_validator('label')
    @classmethod
    def plain_label(cls, value):
        if value is not None and any(char in value for char in '<>'):
            raise ValueError('Tên hiển thị chỉ được chứa văn bản thuần.')
        return value.strip() if value else value

class LayoutWrite(BaseModel):
    device: Literal['mobile', 'desktop']
    revision: int = Field(ge=0)
    items: dict[str, LayoutItem]
    enabled: bool | None = None


def definition_for(key):
    return REGISTRY.get(key.split('--')[0]) if re.fullmatch(r'u-[a-z0-9-]{1,100}', key) else None


def validate_items(items):
    if len(items) > 2000 or any(not (re.fullmatch(r'l-[a-z0-9-]{1,70}', key) or definition_for(key)) for key in items):
        raise HTTPException(400, 'Bố cục không hợp lệ hoặc vượt quá 2.000 thành phần.')
    for key, item in items.items():
        definition = definition_for(key)
        if definition and definition.get('locked') and item.model_dump(exclude_none=True):
            raise HTTPException(400, 'Thành phần này được khóa để bảo đảm thao tác hệ thống.')
        if item.label is not None and (not definition or not (definition.get('label') or definition.get('dynamic_label'))):
            raise HTTPException(400, 'Không thể đổi tên nội dung động hoặc dữ liệu nghiệp vụ.')
        if (item.rows is not None or item.mode is not None) and (not definition or not definition.get('group')):
            raise HTTPException(400, 'Chỉ nhóm nút được thay đổi số dòng.')
        if item.parent and not (re.fullmatch(r'l-[a-z0-9-]{1,70}', item.parent) or definition_for(item.parent)):
            raise HTTPException(400, 'Nhóm bố cục không hợp lệ.')
    return {key: item.model_dump(exclude_none=True) for key, item in items.items()}


def ensure_history(conn):
    conn.execute(text("""CREATE TABLE IF NOT EXISTS vera_ui_layout_audit (
        revision BIGINT PRIMARY KEY, device TEXT NOT NULL, actor TEXT NOT NULL,
        before_json JSONB NOT NULL, after_json JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW())"""))


def read_layout(conn):
    row = conn.execute(text("SELECT value_json,revision FROM vera_app_setting WHERE category='ui' AND setting_key='shared_layout'" )).mappings().first()
    raw = row['value_json'] if row and isinstance(row['value_json'], dict) else {}
    layout = {'desktop': {}, 'mobile': {}}
    for device in ('desktop', 'mobile'):
        for key, value in (raw.get(device, {}) if isinstance(raw.get(device), dict) else {}).items():
            if not isinstance(value, dict):
                continue
            cleaned = {}
            for field, content in value.items():
                if field not in LayoutItem.model_fields:
                    continue
                try:
                    cleaned.update(LayoutItem(**{field: content}).model_dump(exclude_none=True))
                except ValueError:
                    continue
            try:
                layout[device].update(validate_items({key: LayoutItem(**cleaned)}))
            except HTTPException:
                continue
    if '_enabled' in raw: layout['_enabled'] = raw['_enabled'] is not False
    if '_schema_version' in raw: layout['_schema_version'] = 2
    return {'layout': layout, 'revision': int(row['revision']) if row else 0}


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
            ensure_history(conn)
            current = read_layout(conn)
            if current['revision'] != body.revision:
                raise HTTPException(409, 'Bố cục đã được Admin khác cập nhật. Hãy tải lại trước khi sửa.')
            layout = {**current['layout'], body.device: items, '_schema_version': 2}
            if body.enabled is not None:
                layout['_enabled'] = body.enabled
            revision = current['revision'] + 1
            conn.execute(text("""INSERT INTO vera_app_setting(category,setting_key,value_json,source,updated_by,revision,created_at,updated_at)
                VALUES ('ui','shared_layout',CAST(:value AS jsonb),'web_v2',:actor,:revision,NOW(),NOW())
                ON CONFLICT(category,setting_key) DO UPDATE SET value_json=EXCLUDED.value_json,
                updated_by=EXCLUDED.updated_by,revision=EXCLUDED.revision,updated_at=NOW()"""),
                {'value': json.dumps(layout), 'actor': ident.employee_username, 'revision': revision})
            conn.execute(text('''INSERT INTO vera_ui_layout_audit(revision,device,actor,before_json,after_json)
                VALUES(:revision,:device,:actor,CAST(:before AS jsonb),CAST(:after AS jsonb))'''),
                {'revision': revision, 'device': body.device, 'actor': ident.employee_username,
                 'before': json.dumps(current['layout']), 'after': json.dumps(layout)})
            return {'layout': layout, 'revision': revision}

    @app.get('/v2/ui-layout/history')
    def history(ident: identity_type = Depends(current_identity)):
        if str(ident.role).lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được xem lịch sử bố cục.')
        with engine_instance().begin() as conn:
            ensure_history(conn)
            rows = conn.execute(text('SELECT revision,device,actor,created_at FROM vera_ui_layout_audit ORDER BY revision DESC LIMIT 50')).mappings().all()
        return {'items': [dict(row) for row in rows]}

    @app.post('/v2/ui-layout/restore/{revision}')
    def restore(revision: int, body: LayoutWrite, ident: identity_type = Depends(current_identity)):
        if str(ident.role).lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được khôi phục bố cục.')
        with engine_instance().begin() as conn:
            ensure_history(conn)
            row = conn.execute(text('SELECT after_json FROM vera_ui_layout_audit WHERE revision=:revision'), {'revision': revision}).mappings().first()
            if not row:
                raise HTTPException(404, 'Không tìm thấy phiên bản bố cục.')
        items = row['after_json'].get(body.device, {})
        # Ignore retired registry keys while preserving the original legacy IDs.
        items = {key: value for key, value in items.items() if (definition_for(key) and not definition_for(key).get('locked')) or key.startswith('l-')}
        return put_layout(LayoutWrite(device=body.device, revision=body.revision, items=items), ident)
