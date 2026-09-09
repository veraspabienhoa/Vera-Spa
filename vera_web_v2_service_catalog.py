"""Validation and immutable usage terms for server-owned service catalogs."""
from collections import Counter
from copy import deepcopy
from datetime import date
import math
import re
import unicodedata

from fastapi import HTTPException


def _key(value):
    text = unicodedata.normalize("NFD", str(value or "").strip().lower())
    return " ".join("".join(c for c in text if unicodedata.category(c) != "Mn").replace("đ", "d").split())


def _integer(value, label, minimum=0, maximum=100000):
    try:
        number = float(value)
    except (ValueError, TypeError):
        number = math.nan
    if isinstance(value, bool) or not math.isfinite(number) or not number.is_integer() or not minimum <= number <= maximum:
        raise HTTPException(400, f"{label} phải là số nguyên từ {minimum} đến {maximum}.")
    return int(number)


def _date(value, label):
    if value in (None, ""):
        return ""
    try:
        if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
            raise ValueError()
        return date.fromisoformat(value).isoformat()
    except ValueError:
        raise HTTPException(400, f"{label} không hợp lệ.") from None


def catalog_details(kind, incoming, current, services):
    """Validate supplied and saved terms together, preserving old clients' edits."""
    merged = {**(current or {}), **incoming}
    result = {"service_type": "combo" if kind == "combos" else "single"}
    for key, label, limit in [("group", "Nhóm dịch vụ", 120), ("description", "Mô tả", 5000)]:
        value = str(merged.get(key) or "").strip()
        if len(value) > limit:
            raise HTTPException(400, f"{label} tối đa {limit} ký tự.")
        result[key] = value
    result["starts_on"] = _date(merged.get("starts_on"), "Ngày áp dụng")
    unlimited = merged.get("unlimited", True)
    if not isinstance(unlimited, bool):
        raise HTTPException(400, "Vô thời hạn phải là giá trị đúng/sai.")
    result["unlimited"] = unlimited
    result["expires_on"] = "" if unlimited else _date(merged.get("expires_on"), "Ngày hết hạn")
    if not unlimited and (not result["expires_on"] or not result["starts_on"] or result["expires_on"] < result["starts_on"]):
        raise HTTPException(400, "Cần ngày áp dụng và ngày hết hạn; ngày hết hạn không được trước ngày áp dụng.")
    result["loyalty_points"] = _integer(merged.get("loyalty_points", 0), "Điểm tích lũy", maximum=1000000000)
    if kind == "services":
        result["sessions"] = _integer(merged.get("sessions", 1), "Số lượt", minimum=1)
        steps = merged.get("steps", [])
        if not isinstance(steps, list) or len(steps) > 50:
            raise HTTPException(400, "Lộ trình có tối đa 50 bước.")
        result["steps"] = []
        for step in steps:
            if not isinstance(step, dict) or not str(step.get("name") or "").strip() or len(str(step.get("name"))) > 160:
                raise HTTPException(400, "Mỗi bước cần tên, tối đa 160 ký tự.")
            result["steps"].append({"name": str(step["name"]).strip(), "duration": _integer(step.get("duration", 0), "Thời lượng bước", maximum=1440)})
        if sum(step["duration"] for step in result["steps"]) > 1440:
            raise HTTPException(400, "Tổng thời lượng lộ trình không được quá 1440 phút.")
    else:
        # Existing generic ticket packages keep their original meaning.
        components = merged.get("components", [])
        if not isinstance(components, list) or len(components) > 100:
            raise HTTPException(400, "Combo có tối đa 100 dịch vụ thành phần.")
        if "components" in incoming and not components:
            raise HTTPException(400, "Combo cần ít nhất một dịch vụ thành phần.")
        result["components"] = []
        seen = set()
        for component in components:
            if not isinstance(component, dict):
                raise HTTPException(400, "Dịch vụ thành phần không hợp lệ.")
            identifier = str(component.get("service_id") or "")
            service = next((row for row in services if str(row["id"]) == identifier), None)
            if service is None:
                raise HTTPException(400, "Dịch vụ thành phần không tồn tại.")
            if identifier in seen:
                raise HTTPException(400, "Dịch vụ bị trùng trong combo; hãy tăng số lượt ở dòng đã chọn.")
            seen.add(identifier)
            result["components"].append({
                "service_id": identifier, "service_name": service["name"],
                "quantity": _integer(component.get("quantity"), "Số lượt dịch vụ", minimum=1),
            })
        if components:
            result["tickets"] = _integer(sum(row["quantity"] for row in result["components"]), "Tổng lượt combo", minimum=1)
    return result


def require_available(item, day, label):
    if item.get("active") is False:
        raise HTTPException(409, f"{label} đã ngừng sử dụng.")
    today = day.isoformat()
    start = item.get("starts_on") or ""
    end = item.get("expires_on") or ""
    if start and today < start:
        raise HTTPException(409, f"{label} chưa đến ngày áp dụng.")
    if item.get("unlimited", True) is False and end and today > end:
        raise HTTPException(409, f"{label} đã hết hạn sử dụng.")


def purchase_terms(combo, quantity, services, day):
    require_available(combo, day, "Combo")
    terms = {key: deepcopy(combo[key]) for key in ("starts_on", "expires_on", "unlimited") if key in combo}
    if combo.get("components"):
        balances = []
        for item in combo["components"]:
            service = next((row for row in services if row["id"] == item["service_id"]), None)
            if service is None:
                raise HTTPException(409, "Combo có dịch vụ không còn trong danh mục.")
            require_available(service, day, f"Dịch vụ {service['name']}")
            total = item["quantity"] * quantity
            balances.append({"service_id": service["id"], "service_name": service["name"], "total": total, "used": 0, "remaining": total})
        terms["component_balances"] = balances
    return terms


def component_debits(purchase, entries, services, day, *, check_balance=True):
    """Return a validated debit plan; callers commit it with the invoice."""
    require_available(purchase, day, "Combo đã mua")
    if "component_balances" not in purchase:
        return []
    required = Counter()
    for entry in entries:
        if entry.get("service_items"):
            for item in entry["service_items"]:
                required[item["service_id"]] += item["quantity"]
            continue
        name = str(entry.get("service") or "")
        exact = next((row for row in services if _key(row["name"]) == _key(name)), None)
        parts = [name] if exact else [part.strip() for part in name.split("&") if part.strip()]
        for part in parts:
            service = next((row for row in services if _key(row["name"]) == _key(part)), None)
            if not service:
                raise HTTPException(409, f"Không nhận diện được dịch vụ {part} để trừ lượt combo.")
            required[service["id"]] += 1
    balances = purchase["component_balances"]
    plan = []
    for identifier, units in required.items():
        item = next((row for row in balances if row["service_id"] == identifier), None)
        if item is None:
            raise HTTPException(409, "Dịch vụ thanh toán không thuộc combo đã mua.")
        if check_balance and item["remaining"] < units:
            raise HTTPException(409, f"{item['service_name']} trong combo chỉ còn {item['remaining']} lượt.")
        plan.append({"service_id": identifier, "service_name": item["service_name"], "units": units})
    return plan
