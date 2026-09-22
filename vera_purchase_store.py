"""Purchase ledger. Source files and rows stay on the server, never in git."""
from datetime import datetime, date, time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from io import BytesIO
import hashlib
import json
import zipfile

from sqlalchemy import text

VN_TZ = timezone(timedelta(hours=7))
MAX_FILE = 20 * 1024 * 1024


def ensure_schema(conn):
    if conn.execute(text("SELECT to_regclass('vera_purchase_request')")).scalar_one_or_none():
        return
    conn.execute(text("SELECT pg_advisory_xact_lock(726401239)"))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS vera_purchase_source (
      hash text PRIMARY KEY, content bytea NOT NULL, imported_at timestamptz NOT NULL DEFAULT now(),
      actor text NOT NULL, row_count integer NOT NULL, total numeric(20,2) NOT NULL)"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS vera_purchase_entry (
      id bigserial PRIMARY KEY, purchase_date date NOT NULL, item text NOT NULL,
      quantity text NOT NULL, unit_price numeric(20,2) NOT NULL, amount numeric(20,2) NOT NULL,
      note text NOT NULL DEFAULT '', entered_at timestamptz, entered_by text NOT NULL DEFAULT '',
      created_at timestamptz NOT NULL DEFAULT now(), revision integer NOT NULL DEFAULT 0,
      deleted boolean NOT NULL DEFAULT false, source_key text UNIQUE, raw_source jsonb,
      request_key text UNIQUE)"""))
    conn.execute(text("""CREATE TABLE IF NOT EXISTS vera_purchase_audit (
      id bigserial PRIMARY KEY, entry_id bigint NOT NULL, action text NOT NULL,
      before_payload jsonb, after_payload jsonb, actor text NOT NULL,
      created_at timestamptz NOT NULL DEFAULT now())"""))
    conn.execute(text("CREATE INDEX IF NOT EXISTS vera_purchase_date_idx ON vera_purchase_entry(purchase_date DESC,id DESC)"))
    for table in ('vera_purchase_source', 'vera_purchase_entry', 'vera_purchase_audit'):
        conn.execute(text(f'ALTER TABLE {table} ENABLE ROW LEVEL SECURITY'))
        conn.execute(text(f'REVOKE ALL ON {table} FROM PUBLIC'))
    conn.execute(text('''CREATE TABLE IF NOT EXISTS vera_purchase_request (
      key text PRIMARY KEY, fingerprint text NOT NULL, result jsonb NOT NULL)'''))
    conn.execute(text('ALTER TABLE vera_purchase_request ENABLE ROW LEVEL SECURITY'))
    conn.execute(text('REVOKE ALL ON vera_purchase_request FROM PUBLIC'))


def decimal_value(value):
    try:
        result = Decimal(str(value).strip().replace(',', '.'))
        if not result.is_finite() or abs(result) >= Decimal('1e16'):
            raise ValueError('Số tiền/số lượng ngoài giới hạn.')
        return result
    except (InvalidOperation, TypeError):
        raise ValueError('Số tiền/số lượng không hợp lệ.') from None


def source_date(value):
    if value is None or value == '':
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, (float, int)):
        return (datetime(1899, 12, 30) + timedelta(days=value)).date()
    for fmt in ('%Y-%m-%d', '%d-%m-%Y', '%d/%m/%Y'):
        try:
            return datetime.strptime(str(value)[:10], fmt).date()
        except ValueError:
            pass
    raise ValueError('Ngày trong file không hợp lệ.')


def parse_workbook(content):
    """Sniff XLSB/XLSX; retain missing audit metadata and authoritative amounts."""
    if len(content) > MAX_FILE:
        raise ValueError('File tối đa 20 MB.')
    with zipfile.ZipFile(BytesIO(content)) as archive:
        if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024:
            raise ValueError('File giải nén quá lớn.')
        binary = 'xl/workbook.bin' in archive.namelist()
    if binary:
        from pyxlsb import open_workbook
        with open_workbook(BytesIO(content)) as workbook:
            with workbook.get_sheet('Input') as sheet:
                source = [(r[0].r + 1, [c.v for c in r]) for r in sheet.rows()]
    else:
        from openpyxl import load_workbook
        workbook = load_workbook(BytesIO(content), read_only=True, data_only=True)
        try:
            source = list(enumerate(workbook['Input'].values, 1))
        finally:
            workbook.close()
    rows = []
    header = False
    occurrences = {}
    for number, original in source:
        values = list(original) + [None] * 10
        if not header:
            header = str(values[1] or '').strip().lower() == 'chi tiết hàng hóa'
            continue
        if not any(v is not None and v != '' for v in values[:9]):
            continue
        try:
            purchased = source_date(values[0])
            if not purchased or not str(values[1] or '').strip():
                raise ValueError('Thiếu ngày hoặc chi tiết hàng hóa.')
            entered = source_date(values[6])
            clock = values[7]
            if isinstance(clock, (float, int)):
                clock = (datetime.min + timedelta(seconds=round(clock * 86400))).time()
            elif isinstance(clock, str) and clock:
                clock = time.fromisoformat(clock)
            entered_at = datetime.combine(entered, clock or time.min).replace(tzinfo=VN_TZ) if entered else None
            raw = json.dumps(list(original), ensure_ascii=False, default=str)
            fingerprint = hashlib.sha256(raw.encode()).hexdigest()
            occurrences[fingerprint] = occurrences.get(fingerprint, 0) + 1
            rows.append(dict(purchase_date=purchased, item=str(values[1]), quantity=str(values[2]),
                             unit_price=decimal_value(values[3]), amount=decimal_value(values[4]),
                             note=str(values[5] or ''), entered_at=entered_at, entered_by=str(values[8] or ''),
                             source_key=f'{fingerprint}:{occurrences[fingerprint]}', raw_source=raw))
        except (ValueError, TypeError, OverflowError) as exc:
            raise ValueError(f'Dòng {number}: {exc}') from None
    if not header or not rows:
        raise ValueError('Không tìm thấy dữ liệu mua hàng trong sheet Input.')
    return rows


def import_workbook(conn, content, actor, mode='append', rows=None):
    rows = rows if rows is not None else parse_workbook(content)
    digest = hashlib.sha256(content).hexdigest()
    total = sum(r['amount'] for r in rows)
    # Serialize imports, including replacement, within the caller transaction.
    conn.execute(text('SELECT pg_advisory_xact_lock(726401240)'))
    if mode == 'replace':
        for old in conn.execute(text('SELECT * FROM vera_purchase_entry WHERE NOT deleted FOR UPDATE')).mappings():
            audit(conn, old['id'], 'replace', dict(old), None, actor)
        conn.execute(text('UPDATE vera_purchase_entry SET deleted=true, revision=revision+1 WHERE NOT deleted'))
    inserted = 0
    for row in rows:
        result = conn.execute(text('''INSERT INTO vera_purchase_entry
          (purchase_date,item,quantity,unit_price,amount,note,entered_at,entered_by,source_key,raw_source)
          VALUES (:purchase_date,:item,:quantity,:unit_price,:amount,:note,:entered_at,:entered_by,:source_key,CAST(:raw_source AS jsonb))
          ON CONFLICT(source_key) DO NOTHING RETURNING id'''), row).scalar_one_or_none()
        if result is not None:
            inserted += 1
        elif mode == 'replace':
            conn.execute(text('''UPDATE vera_purchase_entry SET purchase_date=:purchase_date,item=:item,
              quantity=:quantity,unit_price=:unit_price,amount=:amount,note=:note,entered_at=:entered_at,
              entered_by=:entered_by,deleted=false,revision=revision+1 WHERE source_key=:source_key'''), row)
    conn.execute(text('''INSERT INTO vera_purchase_source(hash,content,actor,row_count,total)
      VALUES(:hash,:content,:actor,:count,:total) ON CONFLICT(hash) DO NOTHING'''),
      dict(hash=digest,content=content,actor=actor,count=len(rows),total=total))
    return dict(source_rows=len(rows), inserted=inserted, skipped=len(rows)-inserted, total=str(total), sha256=digest)


def server_reconcile_rows(conn):
    """None means not migrated; an empty ledger after deletion stays empty."""
    if not conn.execute(text("SELECT to_regclass('vera_purchase_entry')")).scalar_one_or_none():
        return None
    initialized = conn.execute(text('''SELECT EXISTS(SELECT 1 FROM vera_purchase_source)
      OR EXISTS(SELECT 1 FROM vera_purchase_entry)''')).scalar_one_or_none()
    if not initialized:
        return None
    return [dict(date=r['purchase_date'], date_label=r['purchase_date'].strftime('%d-%m-%Y'),
                 item=r['item'], quantity=r['quantity'], unit_price=float(r['unit_price']),
                 amount=float(r['amount']), buyer=r['note'], user=r['entered_by'])
            for r in conn.execute(text('SELECT * FROM vera_purchase_entry WHERE NOT deleted')).mappings()]


def audit(conn, entry_id, action, before, after, actor):
    conn.execute(text('''INSERT INTO vera_purchase_audit(entry_id,action,before_payload,after_payload,actor)
      VALUES(:id,:action,CAST(:before AS jsonb),CAST(:after AS jsonb),:actor)'''),
      dict(id=entry_id,action=action,before=json.dumps(before,default=str),after=json.dumps(after,default=str),actor=actor))


def require_editable(row, role, revision, today=None):
    if not row or row['deleted']:
        raise KeyError('Không tìm thấy bản ghi.')
    if row['revision'] != revision:
        raise ValueError('Dữ liệu đã thay đổi. Hãy tải lại trước khi thao tác.')
    entered = row['entered_at']
    if role != 'admin' and (not entered or entered.astimezone(VN_TZ).date() != (today or datetime.now(VN_TZ).date())):
        raise PermissionError('Chỉ được sửa/xóa bản ghi nhập trong ngày hiện tại.')
