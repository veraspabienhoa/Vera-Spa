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

class VisualState(BaseModel):
    background: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    gradient: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    text: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    border: str | None = Field(default=None, pattern=r'^#[0-9a-fA-F]{6}$')
    shadow: Literal['none', 'soft', 'medium', 'strong', 'inset', 'raised'] | None = None

class VisualStyle(BaseModel):
    normal: VisualState | None = None
    hover: VisualState | None = None
    pressed: VisualState | None = None
    selected: VisualState | None = None
    focus: VisualState | None = None
    radius: int | None = Field(default=None, ge=0, le=40)
    border_width: int | None = Field(default=None, ge=1, le=6)
    padding_x: int | None = Field(default=None, ge=0, le=40)
    padding_y: int | None = Field(default=None, ge=0, le=32)
    font_size: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    font_weight: Literal[400, 500, 600, 700, 800] | None = None
    font_family: Literal['system', 'segoe', 'roboto', 'serif'] | None = None
    font_style: Literal['normal', 'italic'] | None = None
    glass_blur: int | None = Field(default=None, ge=0, le=20)
    glass_opacity: int | None = Field(default=None, ge=20, le=100)
    depth: int | None = Field(default=None, ge=0, le=8)
    transition_ms: int | None = Field(default=None, ge=0, le=600)
    hover_lift: int | None = Field(default=None, ge=0, le=6)
    press_sink: int | None = Field(default=None, ge=0, le=6)

class LayoutItem(BaseModel):
    hidden: bool | None = None
    custom_kind: Literal['box', 'text', 'frame', 'row', 'search', 'dropdown', 'date', 'table', 'filter'] | None = None
    group_id: str | None = Field(default=None, pattern=r'^g-[a-z0-9-]{1,70}$')
    custom_target: str | None = Field(default=None, pattern=r'^l-custom-[a-z0-9-]{1,70}$')
    custom_options: str | None = Field(default=None, max_length=2000)
    custom_text: str | None = Field(default=None, max_length=2000)
    custom_page: str | None = Field(default=None, pattern=r'^[a-z][a-z0-9-]{0,60}$')
    custom_anchor: str | None = Field(default=None, pattern=r'^[lu]-[a-z0-9-]{1,100}$')
    appearance: VisualStyle | None = None
    order: int | None = Field(default=None, ge=0, le=10000)
    width: int | None = Field(default=None, ge=32, le=2400)
    height: int | None = Field(default=None, ge=24, le=1600)
    offset_x: int | None = Field(default=None, ge=-2400, le=2400)
    offset_y: int | None = Field(default=None, ge=-2400, le=2400)
    text_align: Literal['left', 'center', 'right', 'justify'] | None = None
    content_align: Literal['start', 'center', 'end'] | None = None
    justify_content: Literal['start', 'center', 'end', 'space-between', 'space-around', 'space-evenly'] | None = None
    align_items: Literal['start', 'center', 'end', 'stretch'] | None = None
    gap: int | None = Field(default=None, ge=0, le=100)
    move_to: str | None = Field(default=None, max_length=80)
    parent: str | None = Field(default=None, max_length=80)
    label: str | None = Field(default=None, max_length=100)
    mode: Literal['fit', 'group'] | None = None
    rows: Literal[0, 1, 2, 3, 4] | None = None
    font_size: float | None = Field(default=None, ge=0, allow_inf_nan=False)

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
        if item.custom_kind:
            if not key.startswith('l-custom-') or not item.custom_page or (item.custom_anchor and item.custom_anchor.startswith('l-custom-')):
                raise HTTPException(400, 'Thành phần tùy chỉnh không hợp lệ.')
        elif any(value is not None for value in [item.custom_text, item.custom_page, item.custom_anchor, item.custom_target, item.custom_options]):
            raise HTTPException(400, 'Thiếu loại thành phần tùy chỉnh.')
        definition = definition_for(key)
        if definition and definition.get('locked') and item.model_dump(exclude_none=True):
            raise HTTPException(400, 'Thành phần này được khóa để bảo đảm thao tác hệ thống.')
        if item.label is not None and (not definition or not (definition.get('label') or definition.get('dynamic_label'))):
            raise HTTPException(400, 'Không thể đổi tên nội dung động hoặc dữ liệu nghiệp vụ.')
        if (item.rows is not None or item.mode is not None) and (not definition or not definition.get('group')):
            raise HTTPException(400, 'Chỉ nhóm nút được thay đổi số dòng.')
        if item.custom_target:
            target_item=items.get(item.custom_target)
            if not item.custom_kind or not target_item or target_item.custom_kind != 'table' or target_item.custom_page != item.custom_page:
                raise HTTPException(400, 'Bộ lọc phải liên kết với bảng tự thêm trên cùng trang.')
        if item.move_to:
            destination = definition_for(item.move_to)
            custom_destination=items.get(item.move_to)
            custom_ok=custom_destination and custom_destination.custom_kind in ('frame','row','box')
            if custom_ok and item.custom_kind and item.custom_page != custom_destination.custom_page:
                raise HTTPException(400, 'Chỉ chuyển thành phần tự thêm trong cùng trang.')
            if (not custom_ok and (not destination or not destination.get('group') or destination.get('locked'))) or item.move_to == key:
                raise HTTPException(400, 'Khung đích không hỗ trợ di chuyển.')
            visited = {key}
            target = item.move_to
            while target:
                if target in visited:
                    raise HTTPException(400, 'Không thể di chuyển vòng giữa các khung.')
                visited.add(target)
                target = items[target].move_to if target in items else None
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
