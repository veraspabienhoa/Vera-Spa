"""Independent Quang Ngai cash ledger. Only Admin and Giamdoc may access it."""
from datetime import date, datetime
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Query, Request, Response
from fastapi.responses import StreamingResponse
from starlette.concurrency import run_in_threadpool
from sqlalchemy import text
import vera_quang_ngai_store as revenue_store
import vera_quang_ngai_purchase_store as purchase_store
from vera_web_v2_revenue_leave_list import (
    RevenueEntryCreate, RevenueEntryUpdate, VN_TZ, _range_bounds, _parse_date,
    _revenue_audit_workbook, _revenue_duplicate_workbook,
)
REVENUE_FEATURE = REVENUE_ENTRY_FEATURE = REVENUE_ENTRY_EDIT_FEATURE = REVENUE_ENTRY_DELETE_FEATURE = 'quang_ngai'


def require_role(ident):
    if str(getattr(ident, 'role', '') or '').strip().lower() not in {'admin', 'giamdoc'}:
        raise HTTPException(403, 'Chỉ Admin và Giám đốc được truy cập Quảng Ngãi.')


def prepare_schema(conn):
    revenue_store.ensure_schema(conn)
    purchase_store.ensure_schema(conn)


def lock_ledger(conn):
    if not conn.execute(text('SELECT pg_try_advisory_xact_lock(726401, 92602)')).scalar():
        raise HTTPException(409, 'Quảng Ngãi đang được lưu. Vui lòng thử lại.')


def install_quang_ngai_routes(app, *, engine_instance, current_identity, norm):
    if getattr(app.state, 'quang_ngai_installed', False):
        return
    target = app
    def identity(ident=Depends(current_identity)):
        require_role(ident)
        return ident
    current_identity = identity
    app = APIRouter(dependencies=[Depends(identity)])
    from types import SimpleNamespace
    app.state = SimpleNamespace()
    def require_feature(conn, ident, _feature):
        require_role(ident)
        prepare_schema(conn)
    def feature_allowed(conn, ident, _feature):
        require_role(ident)
        return True

    @app.get('/v2/quang-ngai/summary')
    def summary(time_range: str = 'all', start: date | None = None, end: date | None = None, ident=Depends(current_identity)):
        first, last = _range_bounds(time_range, start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            rows = revenue_store.list_entries(conn, start_date=first, end_date=last)
        income = round(sum(r['amount'] for r in rows if r['type']=='Thu'), 2)
        expense = round(sum(r['amount'] for r in rows if r['type']=='Chi'), 2)
        days = [_parse_date(r.get('date')) for r in rows]
        days = [d for d in days if d]
        today = datetime.now(VN_TZ).date()
        first = first or (min(days) if days else today)
        last = last or (max(days) if days else today)
        return dict(ok=True, source='manual', source_revision=0, entries=rows,
                    total_income=income, total_expense=expense, net_income=round(income-expense,2),
                    balance=round(income-expense,2), total_revenue=income,
                    start_date=first.isoformat(), start_date_label=first.strftime('%d-%m-%Y'),
                    end_date=last.isoformat(), end_date_label=last.strftime('%d-%m-%Y'),
                    current_date=last.isoformat(), current_date_label=last.strftime('%d-%m-%Y'),
                    business_date=today.isoformat(), transaction_count=len(rows),
                    can_create_entry=True, can_edit_entry=True, can_delete_entry=True)

    @app.get('/v2/quang-ngai/revision')
    def revision(response: Response, ident=Depends(current_identity)):
        response.headers['Cache-Control']='no-store'
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            rows=conn.execute(text("""SELECT
              (SELECT concat(COUNT(*),':',COALESCE(MAX(id),0),':',COALESCE(SUM(edit_revision),0)) FROM vera_quang_ngai_entry) AS ledger,
              (SELECT concat(COUNT(*),':',COALESCE(MAX(id),0),':',COALESCE(SUM(revision),0)) FROM vera_quang_ngai_purchase_entry) AS purchases""")).mappings().one()
        return {'revision': f"{rows['ledger']}:{rows['purchases']}:{datetime.now(VN_TZ).date()}"}

    @app.post("/v2/quang-ngai/entry")
    def create_revenue_entry(body: RevenueEntryCreate, ident=Depends(current_identity)):
        income_amount = round(float(body.income_amount or 0), 2)
        expense_amount = round(float(body.expense_amount or 0), 2)
        if income_amount <= 0 and expense_amount <= 0:
            raise HTTPException(400, "Hãy nhập ít nhất một số tiền Thu hoặc Chi lớn hơn 0.")

        entries: list[tuple[str, float, str]] = []
        if income_amount > 0:
            entries.append(("Thu", income_amount, body.income_note))
        if expense_amount > 0:
            entries.append(("Chi", expense_amount, body.expense_note))
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_ENTRY_FEATURE)
            lock_ledger(conn)
            duplicate_rows = revenue_store.find_duplicate_web_entries(conn, entries=entries)
            if duplicate_rows and not body.confirm_duplicate:
                labels = ", ".join(
                    f"{row['transaction_type']} {round(float(row['amount'])):,}đ".replace(",", ".")
                    for row in duplicate_rows
                )
                raise HTTPException(
                    status_code=409,
                    detail={
                        "code": "duplicate_revenue_entry",
                        "message": (
                            f"Phát hiện giao dịch có cùng số tiền và cùng nội dung: {labels}. "
                            "Bạn có muốn vẫn lưu giao dịch này không?"
                        ),
                        "duplicates": duplicate_rows,
                    },
                )
            saved_rows = revenue_store.insert_web_entries(
                conn, transaction_date=body.transaction_date, entries=entries, ident=ident,
            )


        parts = []
        if income_amount > 0:
            parts.append(f"Thu {round(income_amount):,}đ".replace(",", "."))
        if expense_amount > 0:
            parts.append(f"Chi {round(expense_amount):,}đ".replace(",", "."))
        return {
            "ok": True,
            "saved_rows": saved_rows,
            "message": "Đã lưu cùng thời điểm " + " và ".join(parts) + " trên server.",
        }


    @app.post("/v2/quang-ngai/import.xlsx")
    async def import_revenue_excel(request: Request, mode: Literal["append", "replace"] = Query("append"), ident=Depends(current_identity)):
        require_role(ident)
        content = await request.body()
        def process():
            with engine_instance().begin() as conn:
                require_feature(conn, ident, REVENUE_FEATURE)
                lock_ledger(conn)
                try:
                    result = revenue_store.import_ledger_xlsx(
                        conn, content, mode=mode,
                        actor=str(getattr(ident, "employee_username", "") or ""),
                    )
                except ValueError as exc:
                    raise HTTPException(400, str(exc))
            action = "thay thế toàn bộ dữ liệu" if mode == "replace" else "cập nhật dữ liệu mới"
            return {"ok": True, **result, "message": f"Đã {action}: thêm {result['inserted']} dòng, bỏ qua {result['skipped']} dòng trùng."}
        return await run_in_threadpool(process)


    @app.patch("/v2/quang-ngai/entries/{entry_id}")
    def update_revenue_entry(entry_id: int, body: RevenueEntryUpdate, ident=Depends(current_identity)):
        admin_unrestricted = str(getattr(ident, "role", "") or "").strip().lower() in {"admin", "giamdoc"}
        entered_at = None
        if body.entered_date is not None or body.entered_time is not None:
            if body.entered_date is None or not body.entered_time:
                raise HTTPException(400, "Phải nhập đủ Ngày nhập và Giờ nhập.")
            try:
                entered_clock = datetime.strptime(body.entered_time, "%H:%M:%S").time()
            except ValueError:
                try:
                    entered_clock = datetime.strptime(body.entered_time, "%H:%M").time()
                except ValueError:
                    raise HTTPException(400, "Giờ nhập phải đúng HH:MM hoặc HH:MM:SS.")
            entered_at = datetime.combine(body.entered_date, entered_clock).replace(tzinfo=VN_TZ)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_ENTRY_EDIT_FEATURE)
            lock_ledger(conn)
            try:
                result = revenue_store.update_entry(
                    conn, entry_id=entry_id, transaction_type=body.transaction_type,
                    amount=body.amount, transaction_date=body.transaction_date, note=body.note,
                    entered_by_name=body.entered_by_name, entered_at=entered_at,
                    actor=str(getattr(ident, "employee_username", "") or ""),
                    required_entered_date=None if admin_unrestricted else datetime.now(VN_TZ).date(),
                )
            except KeyError:
                raise HTTPException(404, "Không tìm thấy bản ghi doanh thu.")
            except PermissionError:
                raise HTTPException(403, "Chỉ được sửa bản ghi đã nhập trong ngày hiện tại.")
        return {"ok": True, **result, "message": "Đã sửa bản ghi doanh thu."}


    @app.delete("/v2/quang-ngai/entries/{entry_id}")
    def delete_revenue_entry(entry_id: int, ident=Depends(current_identity)):
        admin_unrestricted = str(getattr(ident, "role", "") or "").strip().lower() in {"admin", "giamdoc"}
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_ENTRY_DELETE_FEATURE)
            lock_ledger(conn)
            try:
                revenue_store.soft_delete_entry(
                    conn, entry_id=entry_id,
                    actor=str(getattr(ident, "employee_username", "") or ""),
                    required_entered_date=None if admin_unrestricted else datetime.now(VN_TZ).date(),
                )
            except KeyError:
                raise HTTPException(404, "Không tìm thấy bản ghi doanh thu.")
            except PermissionError:
                raise HTTPException(403, "Chỉ được xóa bản ghi đã nhập trong ngày hiện tại.")
        return {"ok": True, "message": "Đã xóa bản ghi khỏi báo cáo; timestamp lịch sử gốc không thay đổi."}


    @app.get("/v2/quang-ngai/audit")
    def revenue_audit(
        time_range: str = Query("this_month"), start: date | None = Query(None),
        end: date | None = Query(None), ident=Depends(current_identity),
    ):
        require_role(ident)
        start_date, end_date = _range_bounds(time_range, start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            rows = revenue_store.list_audit_entries(conn, start_date=start_date, end_date=end_date)
        return {"ok": True, "rows": rows, "count": len(rows),
                "start_date": start_date.isoformat() if start_date else "",
                "end_date": end_date.isoformat() if end_date else ""}


    @app.get("/v2/quang-ngai/audit/export.xlsx")
    def revenue_audit_export(
        time_range: str = Query("this_month"), start: date | None = Query(None),
        end: date | None = Query(None), ident=Depends(current_identity),
    ):
        require_role(ident)
        start_date, end_date = _range_bounds(time_range, start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            rows = revenue_store.list_audit_entries(conn, start_date=start_date, end_date=end_date)
        filename = f"QuangNgai_LichSu_SuaXoa_ThuChi_{datetime.now(VN_TZ):%d-%m-%Y}.xlsx"
        return StreamingResponse(
            _revenue_audit_workbook(rows),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )


    @app.get("/v2/quang-ngai/duplicates")
    def revenue_duplicates(
        time_range: str = Query("all"), start: date | None = Query(None),
        end: date | None = Query(None), ident=Depends(current_identity),
    ):
        require_role(ident)
        start_date, end_date = _range_bounds(time_range, start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            result = revenue_store.duplicate_analysis(conn, start_date=start_date, end_date=end_date)
        return {"ok": True, **result}


    @app.get("/v2/quang-ngai/duplicates/export.xlsx")
    def revenue_duplicates_export(
        time_range: str = Query("all"), start: date | None = Query(None),
        end: date | None = Query(None), ident=Depends(current_identity),
    ):
        require_role(ident)
        start_date, end_date = _range_bounds(time_range, start, end)
        with engine_instance().begin() as conn:
            require_feature(conn, ident, REVENUE_FEATURE)
            result = revenue_store.duplicate_analysis(conn, start_date=start_date, end_date=end_date)
        filename = f"QuangNgai_KiemTra_DuLieuTrung_ThuChi_{datetime.now(VN_TZ):%d-%m-%Y}.xlsx"
        return StreamingResponse(
            _revenue_duplicate_workbook(result),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    from vera_web_v2_quang_ngai_purchases import install_purchase_routes
    from vera_web_v2_quang_ngai_reconcile import install_purchase_reconcile_routes
    install_purchase_routes(app, engine_instance=engine_instance, current_identity=current_identity,
                            require_feature=require_feature, feature_allowed=feature_allowed)
    install_purchase_reconcile_routes(app, engine_instance=engine_instance, current_identity=current_identity,
                                     require_feature=require_feature, norm=norm, google_client=None)
    target.include_router(app)
    target.state.quang_ngai_installed=True
