"""Small JSON sanitizers shared by VERA's Python services."""

from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
import json
import math
from typing import Any


def json_safe(value: Any) -> Any:
    """Return a JSON-compatible value without turning finite numbers into text."""
    if isinstance(value, dict):
        return {str(key): json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [json_safe(item) for item in value]
    if isinstance(value, Decimal):
        if not value.is_finite():
            return None
        return int(value) if value == value.to_integral_value() else float(value)
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


def json_text(value: Any) -> str:
    """Serialize application data after normalizing database-native scalars."""
    return json.dumps(
        json_safe(value),
        ensure_ascii=False,
        allow_nan=False,
        separators=(",", ":"),
    )
