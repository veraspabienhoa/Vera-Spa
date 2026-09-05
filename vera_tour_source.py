"""Shared PostgreSQL-backed source selection for the TourVera workbook."""
from __future__ import annotations

import os
import re
from typing import Any
from urllib.parse import parse_qs, urlparse


DEFAULT_TOUR_FILE_ID = (
    os.getenv("VERA_TOUR_FILE_ID", "15nDSicFhEHstxQjGrETuSK8Z7q6cSQyS")
    or "15nDSicFhEHstxQjGrETuSK8Z7q6cSQyS"
).strip()
SETTING_CATEGORY = "tour"
SETTING_KEY = "source"
TOUR_MIME = "application/vnd.ms-excel.sheet.macroenabled.12"

_FILE_ID_RE = re.compile(r"^[A-Za-z0-9_-]{20,}$")
_ALLOWED_HOSTS = {
    "drive.google.com",
    "docs.google.com",
    "drive.usercontent.google.com",
}


def extract_tour_file_id(value: Any) -> str:
    """Return a Drive file ID from an ID or a supported Google Drive URL."""
    raw = str(value or "").strip()
    if _FILE_ID_RE.fullmatch(raw):
        return raw
    try:
        parsed = urlparse(raw)
    except Exception as exc:
        raise ValueError("Link TourVera không hợp lệ.") from exc
    if parsed.scheme not in {"http", "https"} or (parsed.hostname or "").lower() not in _ALLOWED_HOSTS:
        raise ValueError("Chỉ chấp nhận link file Google Drive của TourVera.")
    candidates = []
    parts = [part for part in parsed.path.split("/") if part]
    if "d" in parts:
        position = parts.index("d")
        if position + 1 < len(parts):
            candidates.append(parts[position + 1])
    candidates.extend(parse_qs(parsed.query).get("id", []))
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if _FILE_ID_RE.fullmatch(candidate):
            return candidate
    raise ValueError("Không tìm thấy mã file trong link Google Drive.")


def canonical_tour_url(file_id: str) -> str:
    return f"https://drive.google.com/file/d/{extract_tour_file_id(file_id)}/view"


def _configured_payload(default_file_id: str = "") -> dict[str, Any]:
    fallback = str(default_file_id or DEFAULT_TOUR_FILE_ID).strip()
    payload: Any = None
    try:
        import vera_postgres as vpg

        payload = vpg.read_setting(SETTING_CATEGORY, SETTING_KEY, None)
    except Exception:
        payload = None

    if isinstance(payload, dict):
        raw = payload.get("file_id") or payload.get("url")
        try:
            file_id = extract_tour_file_id(raw)
        except ValueError:
            pass
        else:
            return {
                **payload,
                "file_id": file_id,
                "url": canonical_tour_url(file_id),
                "configured": True,
            }
    file_id = extract_tour_file_id(fallback)
    return {
        "file_id": file_id,
        "url": canonical_tour_url(file_id),
        "configured": False,
        "name": "TourVera.xlsm",
    }


def get_tour_source(default_file_id: str = "") -> dict[str, Any]:
    """Read the current shared source, falling back safely to the environment."""
    return _configured_payload(default_file_id)


def get_tour_file_id(default_file_id: str = "") -> str:
    return str(get_tour_source(default_file_id)["file_id"])


def save_tour_source(payload: dict[str, Any], *, updated_by: str) -> dict[str, Any]:
    """Persist a validated source using the application's shared setting table."""
    import vera_postgres as vpg

    file_id = extract_tour_file_id(payload.get("file_id") or payload.get("url"))
    saved = {
        **payload,
        "file_id": file_id,
        "url": canonical_tour_url(file_id),
        "configured": True,
    }
    vpg.write_setting(
        SETTING_CATEGORY,
        SETTING_KEY,
        saved,
        updated_by=str(updated_by or "admin"),
        source="web_v2",
    )
    return saved
