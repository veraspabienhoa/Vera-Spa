"""Canonical official leave-policy document for VERA SPA.

The "Nội quy" page stores the full LoaiNghi grid in PostgreSQL as one versioned
JSON document. Arbitrary user-added columns/rows are preserved. The legacy
Google Sheet LoaiNghi remains a compatibility mirror for older jobs.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

import pandas as pd

CATEGORY = "official_policy"
SETTING_KEY = "leave_rules"
REQUIRED_COLUMNS = (
    "STT",
    "Lý do nghỉ",
    "Loại nghỉ",
    "Số ngày tính phép",
    "Phạt vi phạm",
)
DEFAULT_COLUMNS = [
    "STT", "Lý do nghỉ", "Loại nghỉ", "Chi tiết", "Số ngày tính phép",
    "Phạt vi phạm", "Chỉ nhập được cuối tuần", "User có quyền được nhập",
    "Kiều đăng ký", "Giá trị", "Ngoại trừ đăng ký", "Kiểu hủy",
    "Số ngày hủy trước", "Ngoại trừ hủy", "Ghi chú",
]


class OfficialRulesError(RuntimeError):
    pass


def _clean_scalar(value: Any):
    if value is None:
        return ""
    try:
        if pd.isna(value):
            return ""
    except Exception:
        pass
    if hasattr(value, "item"):
        try:
            return value.item()
        except Exception:
            pass
    return value


def normalize_dataframe(df: pd.DataFrame | None) -> pd.DataFrame:
    if df is None:
        return pd.DataFrame(columns=DEFAULT_COLUMNS)
    if not isinstance(df, pd.DataFrame):
        df = pd.DataFrame(df)
    out = df.copy()
    columns = [str(c or "").strip() for c in out.columns]
    if any(not c for c in columns):
        raise OfficialRulesError("Tên cột không được để trống.")
    if len(set(columns)) != len(columns):
        dupes = sorted({c for c in columns if columns.count(c) > 1})
        raise OfficialRulesError("Tên cột bị trùng: " + ", ".join(dupes))
    out.columns = columns
    out = out.map(_clean_scalar)
    return out.reset_index(drop=True)


def validate_for_apply(df: pd.DataFrame) -> None:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise OfficialRulesError(
            "Không thể áp dụng Nội quy vì thiếu cột nghiệp vụ bắt buộc: "
            + ", ".join(missing)
        )
    if df.empty:
        raise OfficialRulesError("Nội quy không được để trống.")
    reasons = df["Lý do nghỉ"].astype(str).str.strip()
    if reasons.eq("").any():
        bad = [str(i + 2) for i in reasons[reasons.eq("")].index.tolist()[:20]]
        raise OfficialRulesError("Cột Lý do nghỉ đang trống tại dòng: " + ", ".join(bad))
    norm = reasons.str.casefold()
    dupes = reasons[norm.duplicated(keep=False)].drop_duplicates().tolist()
    if dupes:
        raise OfficialRulesError("Lý do nghỉ bị trùng: " + ", ".join(map(str, dupes[:20])))


def dataframe_payload(df: pd.DataFrame) -> dict:
    out = normalize_dataframe(df)
    rows = []
    for record in out.to_dict(orient="records"):
        rows.append({str(k): _clean_scalar(v) for k, v in record.items()})
    payload = {"columns": list(out.columns), "rows": rows}
    raw = json.dumps(payload, ensure_ascii=False, default=str, sort_keys=True, separators=(",", ":"))
    payload["checksum"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    return payload


def payload_dataframe(value: Any) -> pd.DataFrame:
    if not isinstance(value, dict):
        return pd.DataFrame()
    columns = [str(c) for c in value.get("columns", []) if str(c).strip()]
    rows = value.get("rows", [])
    if not isinstance(rows, list):
        rows = []
    if not columns and rows:
        seen = []
        for row in rows:
            if isinstance(row, dict):
                for key in row:
                    key = str(key)
                    if key not in seen:
                        seen.append(key)
        columns = seen
    if not columns:
        return pd.DataFrame()
    clean_rows = []
    for row in rows:
        row = row if isinstance(row, dict) else {}
        clean_rows.append({c: _clean_scalar(row.get(c, "")) for c in columns})
    return pd.DataFrame(clean_rows, columns=columns)


def get_metadata(vpg) -> dict:
    if vpg is None or not callable(getattr(vpg, "get_setting", None)):
        return {}
    row = vpg.get_setting(CATEGORY, SETTING_KEY)
    return dict(row or {})


def load_dataframe(vpg, seed_df: pd.DataFrame | None = None, bootstrap: bool = True) -> pd.DataFrame:
    """Read canonical policy, bootstrapping once from LoaiNghi when missing."""
    if vpg is None or not callable(getattr(vpg, "read_setting", None)):
        return normalize_dataframe(seed_df)
    try:
        if not bool(vpg.is_enabled()):
            return normalize_dataframe(seed_df)
    except Exception:
        return normalize_dataframe(seed_df)

    value = vpg.read_setting(CATEGORY, SETTING_KEY, None)
    current = payload_dataframe(value)
    if not current.empty or (isinstance(value, dict) and value.get("columns")):
        return normalize_dataframe(current)

    seed = normalize_dataframe(seed_df)
    if bootstrap and not seed.empty:
        save_dataframe(vpg, seed, updated_by="system-bootstrap", source="LoaiNghi-bootstrap")
        return seed
    return seed


def save_dataframe(vpg, df: pd.DataFrame, updated_by: str = "", source: str = "noi_quy_page") -> dict:
    if vpg is None or not callable(getattr(vpg, "write_setting", None)):
        raise OfficialRulesError("PostgreSQL chưa sẵn sàng để lưu Nội quy chính thức.")
    try:
        if not bool(vpg.is_enabled()):
            raise OfficialRulesError("PostgreSQL chưa bật; không thể lưu Nội quy chính thức.")
    except OfficialRulesError:
        raise
    except Exception as exc:
        raise OfficialRulesError(f"Không xác định được trạng thái PostgreSQL: {exc}") from exc

    clean = normalize_dataframe(df)
    validate_for_apply(clean)
    return vpg.write_setting(
        CATEGORY,
        SETTING_KEY,
        dataframe_payload(clean),
        updated_by=str(updated_by or ""),
        source=str(source or "noi_quy_page"),
    )
