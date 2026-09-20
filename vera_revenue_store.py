"""PostgreSQL-backed revenue/expense ledger and one-time workbook bootstrap."""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from io import BytesIO
from typing import Any, Callable

from openpyxl import load_workbook
import requests
from sqlalchemy import text


TABLE = "vera_revenue_entry"
SCHEMA_VERSION = 1
VN_TZ = timezone(timedelta(hours=7))
WORKBOOK_EXPORT_URL = "https://docs.google.com/spreadsheets/d/{spreadsheet_id}/export"
HEADERS = [
    "Dấu thời gian", "Loại giao dịch", "Số tiền", "Ngày giao dịch",
    "Ghi chú", "Địa chỉ email", "Tháng", "Ngày nhập", "Giờ nhập", "Người nhập",
]


def ensure_schema(conn) -> None:
    conn.execute(text(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            id bigserial PRIMARY KEY,
            transaction_type text NOT NULL CHECK (transaction_type IN ('Thu','Chi')),
            amount numeric(18,2) NOT NULL CHECK (amount >= 0),
            transaction_date date NULL,
            note text NOT NULL DEFAULT '',
            entered_at timestamptz NOT NULL DEFAULT NOW(),
            entered_by text NOT NULL DEFAULT '',
            entered_by_name text NOT NULL DEFAULT '',
            source_email text NOT NULL DEFAULT '',
            source_name text NOT NULL DEFAULT 'web_v2',
            source_row integer NULL,
            source_month date NULL,
            created_at timestamptz NOT NULL DEFAULT NOW(),
            CONSTRAINT vera_revenue_entry_source_row_uq UNIQUE(source_name, source_row)
        )
    """))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_transaction_date ON {TABLE}(transaction_date DESC, id DESC)"))
    conn.execute(text(f"CREATE INDEX IF NOT EXISTS idx_{TABLE}_entered_at ON {TABLE}(entered_at DESC, id DESC)"))
    conn.execute(text("""
        INSERT INTO vera_schema_version(component,version,updated_at)
        VALUES('revenue_ledger',:version,NOW())
        ON CONFLICT(component) DO UPDATE SET
          version=GREATEST(vera_schema_version.version,EXCLUDED.version), updated_at=NOW()
    """), {"version": SCHEMA_VERSION})


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    raw = str(value or "").strip()
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date()
        except ValueError:
            pass
    return None


def _as_entered_at(value: Any) -> datetime:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, date):
        parsed = datetime.combine(value, time.min)
    else:
        raw = str(value or "").strip()
        parsed = None
        for fmt in ("%d/%m/%Y %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S"):
            try:
                parsed = datetime.strptime(raw.split(".", 1)[0], fmt)
                break
            except ValueError:
                pass
        if parsed is None:
            raise ValueError(f"Thời điểm nhập không hợp lệ: {raw[:30]}")
    return parsed.replace(tzinfo=VN_TZ) if parsed.tzinfo is None else parsed.astimezone(VN_TZ)


def _as_money(value: Any) -> float:
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        return round(float(value), 2)
    raw = "".join(ch for ch in str(value or "") if ch.isdigit() or ch in ",.-")
    if not raw:
        return 0.0
    if "," in raw and "." in raw:
        decimal = "," if raw.rfind(",") > raw.rfind(".") else "."
        thousands = "." if decimal == "," else ","
        raw = raw.replace(thousands, "").replace(decimal, ".")
    elif raw.count(",") == 1 and len(raw.rsplit(",", 1)[1]) <= 2:
        raw = raw.replace(",", ".")
    elif raw.count(".") == 1 and len(raw.rsplit(".", 1)[1]) <= 2:
        pass
    else:
        raw = raw.replace(",", "").replace(".", "")
    return round(float(raw), 2)


def parse_workbook(content: bytes, worksheet_name: str = "Input") -> list[dict[str, Any]]:
    workbook = load_workbook(BytesIO(content), data_only=True, read_only=True)
    if worksheet_name not in workbook.sheetnames:
        raise RuntimeError(f"Workbook không có sheet '{worksheet_name}'.")
    worksheet = workbook[worksheet_name]
    iterator = worksheet.iter_rows(values_only=True)
    headers = [str(value or "").strip() for value in next(iterator, ())]
    required = ["Dấu thời gian", "Loại giao dịch", "Số tiền", "Ngày giao dịch", "Ghi chú", "Địa chỉ email"]
    missing = [name for name in required if name not in headers]
    if missing:
        raise RuntimeError("Sheet Input thiếu cột: " + ", ".join(missing))
    indexes = {name: headers.index(name) for name in headers if name}
    rows: list[dict[str, Any]] = []
    for source_row, raw_tuple in enumerate(iterator, 2):
        raw = list(raw_tuple)
        if not any(value is not None and str(value).strip() for value in raw):
            continue
        tx_type = str(raw[indexes["Loại giao dịch"]] or "").strip().title()
        if tx_type not in {"Thu", "Chi"}:
            raise RuntimeError(f"Dòng {source_row}: Loại giao dịch phải là Thu hoặc Chi.")
        entered_at = _as_entered_at(raw[indexes["Dấu thời gian"]])
        month_index = indexes.get("Tháng")
        rows.append({
            "transaction_type": tx_type,
            "amount": _as_money(raw[indexes["Số tiền"]]),
            "transaction_date": _as_date(raw[indexes["Ngày giao dịch"]]),
            "note": str(raw[indexes["Ghi chú"]] or "").strip(),
            "entered_at": entered_at,
            "source_email": str(raw[indexes["Địa chỉ email"]] or "").strip(),
            "source_month": _as_date(raw[month_index]) if month_index is not None and month_index < len(raw) else None,
            "source_row": source_row,
        })
    if not rows:
        raise RuntimeError("Sheet Input không có giao dịch hợp lệ.")
    return rows


def _actor_by_email(conn) -> dict[str, tuple[str, str]]:
    rows = conn.execute(text("""
        SELECT lower(btrim(COALESCE(email,''))) AS email_key,
               COALESCE(username,'') AS username, COALESCE(full_name,'') AS full_name
        FROM employees WHERE btrim(COALESCE(email,'')) <> ''
    """)).mappings().all()
    return {
        str(row["email_key"]): (str(row["username"]), str(row["full_name"] or row["username"]))
        for row in rows
    }


def import_rows(conn, rows: list[dict[str, Any]], *, source_name: str) -> dict[str, Any]:
    actors = _actor_by_email(conn)
    params = []
    for row in rows:
        email = str(row.get("source_email") or "").strip()
        username, full_name = actors.get(email.lower(), (email, email))
        params.append({
            **row,
            "source_name": source_name,
            "entered_by": username,
            "entered_by_name": full_name,
        })
    before = int(conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one())
    conn.execute(text(f"""
        INSERT INTO {TABLE}(
            transaction_type, amount, transaction_date, note, entered_at,
            entered_by, entered_by_name, source_email, source_name, source_row,
            source_month, created_at
        ) VALUES (
            :transaction_type, :amount, :transaction_date, :note, :entered_at,
            :entered_by, :entered_by_name, :source_email, :source_name, :source_row,
            :source_month, NOW()
        )
        ON CONFLICT(source_name, source_row) DO NOTHING
    """), params)
    after = int(conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one())
    totals = conn.execute(text(f"""
        SELECT COUNT(*) AS row_count,
               COALESCE(SUM(amount) FILTER (WHERE transaction_type='Thu'),0) AS total_income,
               COALESCE(SUM(amount) FILTER (WHERE transaction_type='Chi'),0) AS total_expense
        FROM {TABLE}
    """)).mappings().one()
    return {
        "source_rows": len(rows), "inserted_rows": after - before,
        "row_count": int(totals["row_count"]),
        "total_income": float(totals["total_income"]),
        "total_expense": float(totals["total_expense"]),
    }


def bootstrap_from_google_sheet(
    conn, *, spreadsheet_id: str, worksheet_name: str = "Input",
    http_get: Callable[..., Any] = requests.get,
) -> dict[str, Any]:
    ensure_schema(conn)
    existing = int(conn.execute(text(f"SELECT COUNT(*) FROM {TABLE}")).scalar_one())
    if existing:
        return {"skipped": True, "reason": "ledger_not_empty", "row_count": existing}
    response = http_get(
        WORKBOOK_EXPORT_URL.format(spreadsheet_id=spreadsheet_id),
        params={"format": "xlsx"}, timeout=60,
    )
    response.raise_for_status()
    rows = parse_workbook(bytes(response.content or b""), worksheet_name)
    result = import_rows(conn, rows, source_name=f"google-sheet:{spreadsheet_id}:{worksheet_name}")
    if result["row_count"] != result["source_rows"]:
        raise RuntimeError("Đối soát nhập Thu Chi thất bại: số dòng server khác số dòng nguồn.")
    return {"skipped": False, **result}


def values_from_db(conn) -> list[list[Any]]:
    rows = conn.execute(text(f"""
        SELECT transaction_type, amount, transaction_date, note, entered_at,
               entered_by, source_email, source_month
        FROM {TABLE}
        ORDER BY COALESCE(transaction_date, (entered_at AT TIME ZONE 'Asia/Ho_Chi_Minh')::date), id
    """)).mappings().all()
    values: list[list[Any]] = [list(HEADERS)]
    for row in rows:
        entered = row["entered_at"].astimezone(VN_TZ)
        tx_date = row["transaction_date"]
        values.append([
            entered.strftime("%d/%m/%Y %H:%M:%S"), row["transaction_type"], float(row["amount"]),
            tx_date.strftime("%d/%m/%Y") if tx_date else "", row["note"], row["source_email"],
            row["source_month"].strftime("%d/%m/%Y") if row["source_month"] else "",
            entered.strftime("%d/%m/%Y"), entered.strftime("%H:%M:%S"), row["entered_by"],
        ])
    return values


def insert_web_entries(conn, *, transaction_date: date, entries: list[tuple[str, float, str]], ident) -> int:
    ensure_schema(conn)
    now = datetime.now(VN_TZ)
    actor = str(getattr(ident, "employee_username", "") or "").strip()
    full_name = str(getattr(ident, "full_name", "") or actor).strip() or actor
    email = str(getattr(ident, "email", "") or "").strip()
    params = [{
        "transaction_type": tx_type, "amount": round(float(amount), 2),
        "transaction_date": transaction_date, "note": str(note or "").strip(),
        "entered_at": now, "entered_by": actor, "entered_by_name": full_name,
        "source_email": email,
    } for tx_type, amount, note in entries]
    conn.execute(text(f"""
        INSERT INTO {TABLE}(
            transaction_type, amount, transaction_date, note, entered_at,
            entered_by, entered_by_name, source_email, source_name, created_at
        ) VALUES (
            :transaction_type, :amount, :transaction_date, :note, :entered_at,
            :entered_by, :entered_by_name, :source_email, 'web_v2', NOW()
        )
    """), params)
    return len(params)


def find_duplicate_web_entries(conn, *, entries: list[tuple[str, float, str]]) -> list[dict[str, Any]]:
    """Return prior rows with the same type, amount and normalized note."""
    ensure_schema(conn)
    duplicates: list[dict[str, Any]] = []
    for transaction_type, amount, note in entries:
        normalized_note = str(note or "").strip()
        row = conn.execute(text(f"""
            SELECT transaction_type, amount, transaction_date, note, entered_at
            FROM {TABLE}
            WHERE transaction_type = :transaction_type
              AND amount = :amount
              AND lower(btrim(note)) = lower(:note)
            ORDER BY entered_at DESC, id DESC
            LIMIT 1
        """), {
            "transaction_type": transaction_type,
            "amount": round(float(amount), 2),
            "note": normalized_note,
        }).mappings().first()
        if not row:
            continue
        entered_at = row["entered_at"]
        if entered_at and entered_at.tzinfo is None:
            entered_at = entered_at.replace(tzinfo=timezone.utc)
        duplicates.append({
            "transaction_type": str(row["transaction_type"]),
            "amount": float(row["amount"]),
            "note": str(row["note"] or ""),
            "transaction_date": row["transaction_date"].isoformat() if row["transaction_date"] else None,
            "entered_at": entered_at.astimezone(VN_TZ).isoformat() if entered_at else None,
        })
    return duplicates
