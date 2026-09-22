"""Admin-owned product catalog, independent of bookings and service prices."""
from decimal import Decimal
from typing import Any
from uuid import uuid4
from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import text


class ProductInput(BaseModel):
    sku: str = Field(min_length=1, max_length=60)
    name: str = Field(min_length=1, max_length=150)
    category: str = Field(default='', max_length=120)
    unit: str = Field(default='Cái', min_length=1, max_length=40)
    price: Decimal = Field(default=0, ge=0, le=10000000000, decimal_places=0, allow_inf_nan=False)
    active: bool = True
    note: str = Field(default='', max_length=2000)
    revision: int = Field(default=0, ge=0)

    @field_validator('sku', 'name', 'category', 'unit', 'note', mode='before')
    @classmethod
    def trim(cls, value):
        return str(value).strip() if value is not None else ''


def _schema(conn):
    conn.execute(text('''
        CREATE TABLE IF NOT EXISTS vera_product_catalog (
            id TEXT PRIMARY KEY, sku TEXT NOT NULL, name TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT '', unit TEXT NOT NULL,
            price NUMERIC(14,0) NOT NULL DEFAULT 0 CHECK (price>=0),
            active BOOLEAN NOT NULL DEFAULT TRUE, note TEXT NOT NULL DEFAULT '',
            revision INTEGER NOT NULL DEFAULT 1,
            updated_by TEXT NOT NULL, updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        );
        CREATE UNIQUE INDEX IF NOT EXISTS idx_product_catalog_sku ON vera_product_catalog(lower(sku));
    '''))


def install_product_routes(app, *, engine_instance, current_identity, identity_type: Any):
    def require_admin(ident):
        if str(ident.role or '').lower() != 'admin':
            raise HTTPException(403, 'Chỉ Admin được quản lý danh mục sản phẩm.')

    @app.get('/v2/products')
    def list_products(ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        with engine_instance().begin() as conn:
            _schema(conn)
            rows = conn.execute(text('SELECT * FROM vera_product_catalog ORDER BY lower(name),id')).mappings().all()
            return {'products': [dict(row) for row in rows]}

    @app.post('/v2/products')
    def create_product(body: ProductInput, ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        with engine_instance().begin() as conn:
            _schema(conn)
            row = conn.execute(text('''
                INSERT INTO vera_product_catalog(id,sku,name,category,unit,price,active,note,updated_by)
                VALUES (:id,:sku,:name,:category,:unit,:price,:active,:note,:actor)
                ON CONFLICT (lower(sku)) DO NOTHING RETURNING *
            '''), {**body.model_dump(), 'id':str(uuid4()), 'actor':ident.employee_username}).mappings().first()
            if not row:
                raise HTTPException(409, 'Mã sản phẩm đã tồn tại.')
            return {'product':dict(row)}

    @app.put('/v2/products/{product_id}')
    def update_product(product_id: str, body: ProductInput, ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        from sqlalchemy.exc import IntegrityError
        with engine_instance().begin() as conn:
            _schema(conn)
            try:
                with conn.begin_nested():
                    row = conn.execute(text('''
                        UPDATE vera_product_catalog SET sku=:sku,name=:name,category=:category,
                            unit=:unit,price=:price,active=:active,note=:note,
                            revision=revision+1,updated_by=:actor,updated_at=NOW()
                        WHERE id=:id AND revision=:revision RETURNING *
                    '''), {**body.model_dump(), 'id':product_id, 'actor':ident.employee_username}).mappings().first()
            except IntegrityError:
                raise HTTPException(409, 'Mã sản phẩm đã tồn tại.') from None
            if not row:
                raise HTTPException(409, 'Sản phẩm đã thay đổi. Hãy tải lại trước khi lưu.')
            return {'product':dict(row)}
