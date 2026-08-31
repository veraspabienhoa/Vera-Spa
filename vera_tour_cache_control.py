"""Shared PostgreSQL switch for the Web V2 TourVera cache.

This control is intentionally narrower than Auto Check:
- Admin may pause the frequent TourVera -> PostgreSQL cache refresh used by
  Chấm công / nghỉ giữa ca alerts.
- Auto Check may still read TourVera on its own scheduled/manual run so the
  existing penalty business rules are not silently disabled.
- Web requests never download TourVera directly; when paused they also ignore
  any previously cached TourVera payload immediately.
"""
from __future__ import annotations

import json
from typing import Any

from sqlalchemy import text


CATEGORY = "attendance_tour_cache_control"
SETTING_KEY = "global"
DATASET_KEY = "tourvera_input_today"


def disabled(conn) -> bool:
    value = conn.execute(text("""
        SELECT value_json
        FROM vera_app_setting
        WHERE category=:category AND setting_key=:setting_key
        LIMIT 1
    """), {"category": CATEGORY, "setting_key": SETTING_KEY}).scalar_one_or_none()
    return bool(value.get("disabled")) if isinstance(value, dict) else False


def set_disabled(conn, value: bool, actor: str) -> None:
    payload = {"disabled": bool(value)}
    conn.execute(text("""
        INSERT INTO vera_app_setting(
          category,setting_key,value_json,source,updated_by,revision,created_at,updated_at
        ) VALUES (
          :category,:setting_key,CAST(:value AS jsonb),'web_v2',:actor,1,NOW(),NOW()
        )
        ON CONFLICT(category,setting_key) DO UPDATE SET
          value_json=EXCLUDED.value_json,
          source='web_v2',
          updated_by=EXCLUDED.updated_by,
          revision=vera_app_setting.revision+1,
          updated_at=NOW()
    """), {
        "category": CATEGORY,
        "setting_key": SETTING_KEY,
        "value": json.dumps(payload, ensure_ascii=False),
        "actor": str(actor or "admin").strip() or "admin",
    })


def status(conn) -> dict[str, Any]:
    is_disabled = disabled(conn)
    setting = conn.execute(text("""
        SELECT updated_by, updated_at, revision
        FROM vera_app_setting
        WHERE category=:category AND setting_key=:setting_key
        LIMIT 1
    """), {"category": CATEGORY, "setting_key": SETTING_KEY}).mappings().first()
    cache = conn.execute(text("""
        SELECT updated_at, expires_at, source_version
        FROM vera_dataset_cache
        WHERE dataset_key=:dataset_key
        LIMIT 1
    """), {"dataset_key": DATASET_KEY}).mappings().first()
    return {
        "disabled": is_disabled,
        "enabled": not is_disabled,
        "updated_by": str((setting or {}).get("updated_by") or ""),
        "updated_at": (setting or {}).get("updated_at"),
        "revision": int((setting or {}).get("revision") or 0),
        "cache_updated_at": (cache or {}).get("updated_at"),
        "cache_expires_at": (cache or {}).get("expires_at"),
        "cache_source_version": str((cache or {}).get("source_version") or ""),
        "dataset_key": DATASET_KEY,
    }
