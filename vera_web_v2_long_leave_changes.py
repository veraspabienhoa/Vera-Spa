"""Revision-safe approved-request changes; canonical writes precede worksheet I/O."""
from datetime import date, datetime, timedelta
import json

from fastapi import Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import text

from vera_web_v2_long_leave import (LONG_LEAVE_DATASET, LONG_LEAVE_HEADERS,
    REQUEST_TYPE_ANNUAL, REQUEST_TYPE_RESIGNATION, STATUS_APPROVED, _payload_value, _worksheet)


class ApprovedRequestEdit(BaseModel):
    revision: int = Field(ge=1)
    start_date: date
    end_date: date
    reason: str = Field(default='', max_length=1000)
    detail: str = Field(default='', max_length=5000)


class ApprovedRequestCancel(BaseModel):
    revision: int = Field(ge=1)
    note: str = Field(min_length=1, max_length=2000)


def ensure_audit(conn):
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_long_leave_change (
        id bigserial PRIMARY KEY, request_id text NOT NULL, actor text NOT NULL,
        action text NOT NULL, before_payload jsonb NOT NULL, after_payload jsonb NOT NULL,
        removed_rows jsonb NOT NULL, added_uids jsonb NOT NULL,
        mirror_pending boolean NOT NULL DEFAULT true, syncing_until timestamptz,
        created_at timestamptz NOT NULL DEFAULT now())'''))


def mutate(conn, request_id, body, ident, *, cancel, request_row, norm,
           validate_and_prepare, leave_create_type, insert_record, vn_tz):
    # Same lock order as approval. All quota reads and daily writes reuse conn.
    conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase14:long_leave'))"))
    ensure_audit(conn)
    if conn.execute(text('SELECT 1 FROM vera_long_leave_change WHERE request_id=:id AND mirror_pending LIMIT 1'),
                    {'id': request_id}).first():
        raise HTTPException(409, 'Đơn đang chờ đồng bộ lần sửa trước. Hãy đồng bộ trước khi sửa tiếp.')
    row = request_row(conn, request_id, lock=True)
    if not row:
        raise HTTPException(404, 'Không tìm thấy đơn.')
    if row['record_status'] != STATUS_APPROVED:
        raise HTTPException(409, 'Chỉ sửa hoặc hủy được đơn đã duyệt.')
    if int(row['revision']) != body.revision:
        raise HTTPException(409, 'Đơn đã thay đổi. Hãy làm mới trước khi thao tác.')
    old = _payload_value(row['payload'])
    payload = dict(old)
    employee = str(old.get('Tên nhân viên') or '').strip()
    request_type = str(row['record_type'] or old.get('Loại đơn') or '')
    if not employee:
        raise HTTPException(409, 'Đơn thiếu nhân viên; cần đối chiếu trước khi sửa.')
    if not cancel:
        days = (body.end_date - body.start_date).days + 1
        if days < 1 or days > 367 or (norm(request_type) == norm(REQUEST_TYPE_ANNUAL) and days > 7):
            raise HTTPException(400, 'Khoảng ngày không hợp lệ; Phép năm tối đa 7 ngày.')
        if norm(request_type) == norm(REQUEST_TYPE_RESIGNATION) and days != 1:
            raise HTTPException(400, 'Đơn nghỉ việc chỉ dùng một ngày dự kiến.')
        payload.update({'Từ ngày': body.start_date.strftime('%d/%m/%Y'),
            'Đến ngày': body.end_date.strftime('%d/%m/%Y'),
            'Lý do nghỉ dài hạn': body.reason.strip(), 'Chi tiết': body.detail.strip()})
    else:
        if not body.note.strip():
            raise HTTPException(400, 'Cần nhập lý do hủy đơn.')
        payload.update({'Trạng thái': 'Đã hủy', 'Lý do hủy': body.note.strip(),
                        'Trạng thái kỳ nghỉ': 'Đã hủy'})
    removed, added = [], []
    if norm(request_type) == norm(REQUEST_TYPE_ANNUAL):
        conn.execute(text("SELECT pg_advisory_xact_lock(hashtext('vera:phase4:leave_primary'))"))
        tag = f'Phép năm được Admin duyệt từ đơn {request_id}'
        owned = conn.execute(text('''SELECT * FROM leave_records
            WHERE lower(btrim(employee_name))=lower(btrim(:employee)) AND detail=:tag
            FOR UPDATE'''), {'employee': employee, 'tag': tag}).mappings().all()
        if any(norm(r['leave_reason']) != norm(REQUEST_TYPE_ANNUAL) for r in owned):
            raise HTTPException(409, 'Lịch nghỉ của đơn đã được sửa riêng. Hãy đối chiếu trước khi hủy/sửa đơn.')
        wanted = set() if cancel else {body.start_date + timedelta(days=n) for n in range(days)}
        kept = {r['leave_date'] for r in owned if r['leave_date'] in wanted}
        for item in owned:
            if item['leave_date'] not in wanted:
                removed.append(dict(item))
                conn.execute(text('DELETE FROM leave_records WHERE record_uid=:uid'), {'uid': item['record_uid']})
        for day in sorted(wanted - kept):
            record, _ = validate_and_prepare(conn, leave_create_type(leave_date=day,
                employee_name=employee, leave_reason=REQUEST_TYPE_ANNUAL, detail=tag),
                ident, skip_registration_timing=True)
            insert_record(conn, record, None)
            added.append(record['record_uid'])
    payload['Người cập nhật'] = ident.employee_username
    payload['Cập nhật lúc'] = datetime.now(vn_tz).strftime('%d/%m/%Y %H:%M:%S')
    ensure_audit(conn)
    audit_id = conn.execute(text('''INSERT INTO vera_long_leave_change
        (request_id,actor,action,before_payload,after_payload,removed_rows,added_uids)
        VALUES(:id,:actor,:action,CAST(:before AS jsonb),CAST(:after AS jsonb),
               CAST(:removed AS jsonb),CAST(:added AS jsonb)) RETURNING id'''),
        {'id': request_id, 'actor': ident.employee_username, 'action': 'cancel' if cancel else 'edit',
         'before': json.dumps(dict(row), ensure_ascii=False, default=str),
         'after': json.dumps(payload, ensure_ascii=False),
         'removed': json.dumps(removed, ensure_ascii=False, default=str), 'added': json.dumps(added)}).scalar_one()
    conn.execute(text('''UPDATE vera_phase14_record SET payload=CAST(:payload AS jsonb),
        record_status=:status,date_from=:start,date_to=:end,updated_by=:actor,
        revision=revision+1,updated_at=now() WHERE dataset=:dataset AND logical_id=:id'''),
        {'payload': json.dumps(payload, ensure_ascii=False), 'status': payload.get('Trạng thái', STATUS_APPROVED),
         'start': row['date_from'] if cancel else payload['Từ ngày'],
         'end': row['date_to'] if cancel else payload['Đến ngày'],
         'actor': ident.employee_username, 'dataset': LONG_LEAVE_DATASET, 'id': row['logical_id']})
    return audit_id


def install(app, *, engine_instance, current_identity, identity_type, norm, google_client,
            leave_sheet_id, vn_tz, validate_and_prepare, leave_create_type,
            sheet_row_for_record, insert_record, request_row, require_admin, sheet_request_row):
    def sync(request_id):
        # Every connection is closed before worksheet/network access.
        with engine_instance().begin() as conn:
            ensure_audit(conn)
            row = request_row(conn, request_id)
            if not row:
                raise HTTPException(404, 'Không tìm thấy đơn.')
            events = [dict(r) for r in conn.execute(text('''UPDATE vera_long_leave_change
                SET syncing_until=now()+interval '5 minutes'
                WHERE request_id=:id AND mirror_pending
                  AND (syncing_until IS NULL OR syncing_until<now()) RETURNING *'''), {'id': request_id}).mappings()]
            if not events:
                return bool(conn.execute(text('SELECT 1 FROM vera_long_leave_change WHERE request_id=:id AND mirror_pending'),
                                         {'id': request_id}).first())
            row = dict(row)
            added = []
            for event in events:
                for uid in event['added_uids']:
                    daily = conn.execute(text('SELECT * FROM leave_records WHERE record_uid=:uid'), {'uid': uid}).mappings().first()
                    if daily:
                        added.append(dict(daily))
        try:
            ws = _worksheet(google_client, leave_sheet_id)
            number, _ = sheet_request_row(ws, request_id, row['source_row'])
            payload = _payload_value(row['payload'])
            ws.update(range_name=f'A{number}:Z{number}',
                values=[[payload.get(h, '') for h in LONG_LEAVE_HEADERS]], value_input_option='USER_ENTERED')
            if added or any(e['removed_rows'] for e in events):
                daily_ws = google_client().open_by_key(leave_sheet_id).get_worksheet(0)
                values = daily_ws.get_all_values()
                headers = [norm(h) for h in values[0]]
                def cell(cells, key):
                    index = headers.index(norm(key))
                    return str(cells[index] if index < len(cells) else '').strip()
                from vera_web_v2_long_leave import _parse_vn_date
                for event in events:
                    for old in event['removed_rows']:
                        for number, cells in enumerate(values[1:], 2):
                            if (cell(cells, 'Chi tiết') == old['detail'] and
                                norm(cell(cells, 'Tên nhân viên')) == norm(old['employee_name']) and
                                str(_parse_vn_date(cell(cells, 'Ngày'))) == old['leave_date'] and
                                norm(cell(cells, 'Lý do nghỉ')) == norm(REQUEST_TYPE_ANNUAL)):
                                daily_ws.batch_clear([f'A{number}:M{number}'])
                source_rows = []
                for record in added:
                    current = daily_ws.get_all_values()
                    existing = next((n for n, cells in enumerate(current[1:], 2)
                        if cell(cells, 'Chi tiết') == record['detail'] and
                        norm(cell(cells, 'Tên nhân viên')) == norm(record['employee_name']) and
                        _parse_vn_date(cell(cells, 'Ngày')) == record['leave_date']), None)
                    if existing is None:
                        number, cells = sheet_row_for_record(daily_ws, record)
                        daily_ws.update(range_name=f'A{number}:M{number}', values=[cells], value_input_option='USER_ENTERED')
                    else:
                        number = existing
                    source_rows.append((record['record_uid'], number))
                with engine_instance().begin() as conn:
                    for uid, number in source_rows:
                        conn.execute(text('UPDATE leave_records SET source_row=:number WHERE record_uid=:uid'),
                                     {'number': number, 'uid': uid})
            with engine_instance().begin() as conn:
                for event in events:
                    conn.execute(text('UPDATE vera_long_leave_change SET mirror_pending=false WHERE id=:id'), {'id': event['id']})
            return False
        except Exception:
            with engine_instance().begin() as conn:
                for event in events:
                    conn.execute(text('UPDATE vera_long_leave_change SET syncing_until=NULL WHERE id=:id'), {'id': event['id']})
            return True

    def change(request_id, body, ident, cancel):
        require_admin(ident)
        with engine_instance().begin() as conn:
            mutate(conn, request_id, body, ident, cancel=cancel, request_row=request_row, norm=norm,
                validate_and_prepare=validate_and_prepare, leave_create_type=leave_create_type,
                insert_record=insert_record, vn_tz=vn_tz)
        pending = sync(request_id)
        return {'ok': True, 'mirror_pending': pending,
                'message': ('Đã hủy đơn và gỡ lịch nghỉ của đơn.' if cancel else 'Đã sửa đơn đã duyệt.') +
                    (' Dữ liệu máy chủ đã lưu; bảng dữ liệu cũ đang chờ đồng bộ.' if pending else '')}

    @app.put('/v2/long-leave/admin/requests/{request_id}')
    def edit(request_id: str, body: ApprovedRequestEdit, ident: identity_type = Depends(current_identity)):
        return change(request_id, body, ident, False)

    @app.delete('/v2/long-leave/admin/requests/{request_id}')
    def cancel(request_id: str, body: ApprovedRequestCancel, ident: identity_type = Depends(current_identity)):
        return change(request_id, body, ident, True)

    @app.post('/v2/long-leave/admin/requests/{request_id}/sync')
    def retry_sync(request_id: str, ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        return {'ok': True, 'mirror_pending': sync(request_id)}

    @app.get('/v2/long-leave/admin/pending-changes')
    def pending_changes(ident: identity_type = Depends(current_identity)):
        require_admin(ident)
        with engine_instance().begin() as conn:
            ensure_audit(conn)
            ids = list(conn.execute(text('SELECT DISTINCT request_id FROM vera_long_leave_change WHERE mirror_pending ORDER BY request_id')).scalars())
        return {'request_ids': ids}
