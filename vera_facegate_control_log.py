"""Read-only, privacy-minimized FaceGate Control and Capture Log clients.

The observed responses are flat ``root.CONTROL.*=value`` and
``root.CAPTURE.*=value`` documents. Control logs keep only event ID, time,
display name and raw status. Capture logs expose file pointers so an Admin can
request one image through the device's observed ``/webs/getImage`` endpoint.
Images are returned on demand and are never persisted by this module.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
import html
import os
import re
import secrets
from typing import Any
from urllib.parse import urlsplit

import requests


VN_TZ = timezone(timedelta(hours=7))
DEFAULT_PATH = "/webs/getControl"
MAX_PAGE_SIZE = 20
MAX_RECORDS = 2000
MAX_RESPONSE_BYTES = 256 * 1024
_FIELD = re.compile(
    r"root\.(?P<section>CONTROL|CAPTURE|ERR)\.(?P<key>[A-Za-z0-9_.]+)="
    r"(?P<value>.*?)(?=\s+root\.(?:CONTROL|CAPTURE|ERR)\.|</html>|$)", re.DOTALL,
)
_ITEM_KEY = re.compile(r"ITEM(?P<index>\d+)\.(?P<field>[A-Za-z0-9_]+)\Z")
DEFAULT_CAPTURE_PATH = "/webs/getCapture"
DEFAULT_IMAGE_PATH = "/webs/getImage"


def registration_ref(item: dict[str, Any]) -> dict[str, int] | None:
    try:
        values = [int(item[name]) for name in ("dwfiletype", "dwfileindex", "dwfilepos")]
    except (KeyError, TypeError, ValueError):
        return None
    if values[0] != 0 or not 0 <= values[1] <= 65535 or not 0 < values[2] <= 2**63 - 1:
        return None
    return dict(zip(("file_type", "file_index", "file_position"), values))


def mapping_device_id() -> str:
    value = os.getenv("VERA_FACEGATE_DEVICE_ID", "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
        raise RuntimeError("Cần cấu hình mã thiết bị FaceGate trước khi ánh xạ.")
    return value


def fetch_registered_profile(uid: int, *, get=requests.get) -> dict[str, Any]:
    if not 0 < uid <= 2**31 - 1:
        raise ValueError("ID hồ sơ FaceGate không hợp lệ.")
    base_url, _, auth = _facegate_config()
    try:
        response = get(f"{base_url}/webs/getWhitelist", params={
            "action": "list", "group": "LIST", "LIST.uid": str(uid),
            "RanId": str(secrets.randbelow(90_000_000) + 10_000_000),
        }, auth=auth, timeout=(3, 8), allow_redirects=False)
    except requests.RequestException as exc:
        raise ConnectionError("Không đọc được hồ sơ FaceGate.") from exc
    try:
        if response.status_code != 200:
            raise ConnectionError("FaceGate không chấp nhận truy vấn hồ sơ.")
        body = str(response.text or "")
        if len(body.encode("utf-8")) > MAX_RESPONSE_BYTES:
            raise ValueError("Phản hồi hồ sơ FaceGate vượt giới hạn.")
        fields = dict(re.findall(
            r"root\.((?:LIST|ERR)\.[A-Za-z0-9_]+)=(.*?)(?=\s+root\.|</html>|$)", body, re.DOTALL))
        fields = {key: html.unescape(value).strip() for key, value in fields.items()}
        if fields.get("ERR.no") != "0" or fields.get("LIST.uid") != str(uid):
            raise ValueError("FaceGate không trả đúng hồ sơ được yêu cầu.")
        ref = registration_ref({key.removeprefix("LIST."): value for key, value in fields.items()})
        if ref is None:
            raise ValueError("Hồ sơ chưa có tham chiếu ảnh đăng ký hợp lệ.")
        return {"profile_id": uid, "device_name": fields.get("LIST.uname", "")[:160],
                "registration_ref": ref}
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()
MAX_IMAGE_BYTES = 4 * 1024 * 1024
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/gif", "image/webp", "image/bmp", "image/x-ms-bmp"}


def parse_control_log_response(body: str) -> dict[str, Any]:
    """Parse the device's plain-text HTML response, discarding non-event PII."""
    values: dict[str, str] = {}
    items: dict[int, dict[str, str]] = {}
    for match in _FIELD.finditer(str(body or "")):
        section = match.group("section")
        key = match.group("key")
        value = html.unescape(match.group("value")).strip()
        if section == "ERR":
            values[f"ERR.{key}"] = value
            continue
        item_match = _ITEM_KEY.fullmatch(key)
        if item_match:
            index = int(item_match.group("index"))
            if index < MAX_PAGE_SIZE:
                items.setdefault(index, {})[item_match.group("field")] = value
        else:
            values[key] = value

    if values.get("ERR.no") is None:
        raise ValueError("Phản hồi FaceGate không đúng định dạng Control Log.")
    if values["ERR.no"] != "0":
        raise ValueError("FaceGate trả lỗi khi đọc Control Log.")
    if "totalcount" not in values:
        raise ValueError("Phản hồi FaceGate không đúng định dạng Control Log.")
    try:
        total_count = max(0, int(values.get("totalcount", "0")))
        session_id = max(0, int(values.get("sessionid", "0")))
        response_count = max(0, int(values.get("rspcount", "0")))
        begin_no = max(0, int(values.get("beginno", "0")))
    except ValueError as exc:
        raise ValueError("Phản hồi FaceGate có bộ đếm không hợp lệ.") from exc

    records = []
    for index in sorted(items):
        item = items[index]
        try:
            event_id = int(item.get("uid", ""))
            device_time = datetime.strptime(item.get("utime", ""), "%Y-%m-%d/%H:%M:%S").replace(tzinfo=VN_TZ)
        except (TypeError, ValueError):
            continue
        display_name = item.get("uname", "").strip()
        if not display_name:
            continue
        records.append({
            "event_id": event_id,
            "occurred_at": device_time.isoformat(),
            "device_name": display_name[:160],
            "status_code": item.get("ustatus", "")[:32],
            "type_code": item.get("utype", "")[:32],
            "registration_ref": registration_ref(item),
        })

    return {
        "session_id": session_id,
        "total_count": total_count,
        "begin_no": begin_no,
        "response_count": response_count,
        "records": records,
    }


def _facegate_config(path_env: str = "VERA_FACEGATE_CONTROL_LOG_PATH", default_path: str = DEFAULT_PATH) -> tuple[str, str, tuple[str, str]]:
    base_url = str(os.getenv("VERA_FACEGATE_BASE_URL", "") or "").strip().rstrip("/")
    path = str(os.getenv(path_env, default_path) or default_path).strip()
    username = str(os.getenv("VERA_FACEGATE_USERNAME", "") or "")
    password = str(os.getenv("VERA_FACEGATE_PASSWORD", "") or "")
    parts = urlsplit(base_url)
    if parts.scheme not in {"http", "https"} or not parts.hostname or parts.username or parts.password:
        raise RuntimeError("FaceGate chưa được cấu hình qua đường kết nối nội bộ.")
    if not username or not password:
        raise RuntimeError("FaceGate chưa được cấu hình xác thực phía máy chủ.")
    if not path.startswith("/") or "?" in path or "#" in path or ".." in path:
        raise RuntimeError("Đường dẫn Control Log FaceGate không hợp lệ.")
    return base_url, path, (username, password)


def _parse_capture_log_response(body: str) -> dict[str, Any]:
    values: dict[str, str] = {}
    items: dict[int, dict[str, str]] = {}
    for match in _FIELD.finditer(str(body or "")):
        section, key = match.group("section"), match.group("key")
        value = html.unescape(match.group("value")).strip()
        if section == "ERR":
            values[f"ERR.{key}"] = value
        elif section == "CAPTURE":
            item_match = _ITEM_KEY.fullmatch(key)
            if item_match:
                index = int(item_match.group("index"))
                if index < MAX_PAGE_SIZE:
                    items.setdefault(index, {})[item_match.group("field")] = value
            else:
                values[key] = value

    if values.get("ERR.no") is None:
        raise ValueError("Phản hồi FaceGate không đúng định dạng Capture Log.")
    if values["ERR.no"] != "0":
        raise ValueError("FaceGate trả lỗi khi đọc Capture Log.")
    if "totalcount" not in values:
        raise ValueError("Phản hồi FaceGate không đúng định dạng Capture Log.")
    try:
        total_count = max(0, int(values.get("totalcount", "0")))
        session_id = max(0, int(values.get("sessionid", "0")))
        response_count = max(0, int(values.get("rspcount", "0")))
    except ValueError as exc:
        raise ValueError("Phản hồi FaceGate có bộ đếm không hợp lệ.") from exc

    records = []
    for item in items.values():
        try:
            event_id = int(item.get("uid", ""))
            occurred = datetime.strptime(item.get("utime", ""), "%Y-%m-%d/%H:%M:%S").replace(tzinfo=VN_TZ)
            file_type = int(item.get("dwfiletype", "-1"))
            file_index = int(item.get("dwfileindex", "-1"))
            file_position = int(item.get("dwfilepos", "-1"))
        except (TypeError, ValueError):
            continue
        records.append({
            "event_id": event_id,
            "occurred_at": occurred.isoformat(),
            "image_ref": {
                "file_type": file_type,
                "file_index": file_index,
                "file_position": file_position,
                "time": occurred.strftime("%Y-%m-%d/%H:%M:%S"),
            },
            "image_available": file_type == 2 and file_index >= 0 and file_position > 0,
            "event_text": item.get("utext", "")[:80],
            "event_status": item.get("udescription", "")[:80],
        })

    return {
        "session_id": session_id,
        "total_count": total_count,
        "response_count": response_count,
        "records": records,
    }


def _close_query_session(base_url: str, path: str, auth: tuple[str, str],
                         group: str, session_id: int, post) -> None:
    """Release a device query session without masking the original read result."""
    if session_id <= 0:
        return
    try:
        response = post(
            f"{base_url}{path}",
            params={"action": "msg", "group": group, "sessionid": str(session_id),
                    "RanId": str(secrets.randbelow(90_000_000) + 10_000_000)},
            timeout=(3, 8), allow_redirects=False, auth=auth,
        )
        close = getattr(response, "close", None)
        if callable(close):
            close()
    except requests.RequestException:
        pass


def fetch_capture_log(start: str, end: str, *, get=requests.get, post=requests.post) -> dict[str, Any]:
    """Fetch bounded Capture Log metadata. This endpoint does not fetch images."""
    base_url, path, auth = _facegate_config("VERA_FACEGATE_CAPTURE_LOG_PATH", DEFAULT_CAPTURE_PATH)
    begin_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if end_date < begin_date or (end_date - begin_date).days > 62:
        raise ValueError("Khoảng ngày Capture Log không hợp lệ (tối đa 63 ngày).")

    records: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    begin_no = 0
    session_id = 0
    total_count = None
    truncated = False
    try:
      while begin_no < MAX_RECORDS:
        params = {
            "action": "list", "group": "CAPTURE", "begintime": f"{begin_date.isoformat()}/00:00:00",
            "endtime": f"{end_date.isoformat()}/23:59:59", "utype": "0", "sequence": "1",
            "beginno": str(begin_no), "reqcount": str(MAX_PAGE_SIZE), "sessionid": str(session_id),
            "RanId": str(secrets.randbelow(90_000_000) + 10_000_000),
        }
        try:
            response = get(f"{base_url}{path}", params=params, timeout=(3, 8), allow_redirects=False, auth=auth)
        except requests.RequestException as exc:
            raise ConnectionError("Không kết nối được FaceGate Capture Log qua relay VPS.") from exc
        if int(getattr(response, "status_code", 0)) != 200:
            raise ConnectionError("FaceGate không chấp nhận truy vấn Capture Log.")
        body = str(getattr(response, "text", "") or "")
        if len(body.encode("utf-8", errors="ignore")) > MAX_RESPONSE_BYTES:
            raise ValueError("Phản hồi FaceGate vượt giới hạn an toàn.")
        page = _parse_capture_log_response(body)
        total_count = page["total_count"] if total_count is None else total_count
        session_id = page["session_id"] or session_id
        for record in page["records"]:
            if record["event_id"] not in seen_ids:
                seen_ids.add(record["event_id"])
                records.append(record)
        received = page["response_count"] or len(page["records"])
        if received > MAX_PAGE_SIZE:
            raise ValueError("FaceGate trả số bản ghi vượt giới hạn mỗi trang.")
        if received <= 0:
            break
        begin_no += received
        if begin_no >= total_count:
            break
      else:
        truncated = total_count is not None and total_count > MAX_RECORDS
    finally:
      _close_query_session(base_url, path, auth, "CAPTURE", session_id, post)
    return {
        "source": "facegate_capture_log", "records": records, "count": len(records),
        "total_count": int(total_count or 0), "truncated": truncated,
        "employee_mapping_verified": False,
    }


def fetch_capture_image(ref: dict[str, Any], *, get=requests.get) -> tuple[bytes, str]:
    """Proxy one on-demand image using file references from a Capture Log row."""
    base_url, path, auth = _facegate_config("VERA_FACEGATE_IMAGE_PATH", DEFAULT_IMAGE_PATH)
    try:
        file_type = int(ref["file_type"])
        file_index = int(ref["file_index"])
        file_position = int(ref["file_position"])
        occurred = datetime.strptime(str(ref["time"]), "%Y-%m-%d/%H:%M:%S")
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Tham chiếu ảnh FaceGate không hợp lệ.") from exc
    if not (0 <= file_type <= 255 and 0 <= file_index <= 65535 and 0 <= file_position <= 2**63 - 1):
        raise ValueError("Tham chiếu ảnh FaceGate vượt giới hạn.")
    params = {
        "action": "list", "group": "IMAGE", "dwfiletype": str(file_type),
        "dwfileindex": str(file_index), "dwfilepos": str(file_position),
        "time": occurred.strftime("%Y-%m-%d/%H:%M:%S"),
        "RanId": str(secrets.randbelow(90_000_000) + 10_000_000),
    }
    try:
        response = get(f"{base_url}{path}", params=params, timeout=(3, 8), allow_redirects=False, auth=auth, stream=True)
    except requests.RequestException as exc:
        raise ConnectionError("Không tải được ảnh capture từ FaceGate qua relay VPS.") from exc
    try:
        if int(getattr(response, "status_code", 0)) != 200:
            raise ConnectionError("FaceGate không trả ảnh capture.")
        headers = getattr(response, "headers", {}) or {}
        media_type = str(headers.get("Content-Type", "")).split(";", 1)[0].strip().lower()
        if media_type not in ALLOWED_IMAGE_TYPES:
            raise ValueError("FaceGate không trả về định dạng ảnh được hỗ trợ.")
        chunks = []
        size = 0
        iter_content = getattr(response, "iter_content", None)
        if callable(iter_content):
            for chunk in iter_content(chunk_size=64 * 1024):
                if not chunk:
                    continue
                size += len(chunk)
                if size > MAX_IMAGE_BYTES:
                    raise ValueError("Ảnh FaceGate vượt giới hạn an toàn.")
                chunks.append(chunk)
            data = b"".join(chunks)
        else:
            data = bytes(getattr(response, "content", b"") or b"")
            if len(data) > MAX_IMAGE_BYTES:
                raise ValueError("Ảnh FaceGate vượt giới hạn an toàn.")
        if not data:
            raise ValueError("FaceGate trả ảnh rỗng.")
        return data, media_type
    finally:
        close = getattr(response, "close", None)
        if callable(close):
            close()


def fetch_control_log(start: str, end: str, *, get=requests.get, post=requests.post) -> dict[str, Any]:
    """Fetch a bounded range of Control Log pages through a configured relay."""
    base_url, path, auth = _facegate_config()
    begin_date = datetime.strptime(start, "%Y-%m-%d").date()
    end_date = datetime.strptime(end, "%Y-%m-%d").date()
    if end_date < begin_date or (end_date - begin_date).days > 62:
        raise ValueError("Khoảng ngày Control Log không hợp lệ (tối đa 63 ngày).")

    records: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    begin_no = 0
    session_id = 0
    total_count = None
    truncated = False
    try:
      while begin_no < MAX_RECORDS:
        params = {
            "action": "list",
            "group": "CONTROL",
            "ustatus": "0",
            "usex": "2",
            "uage": "0-100",
            "MjCardNo": "0",
            "begintime": f"{begin_date.isoformat()}/00:00:00",
            "endtime": f"{end_date.isoformat()}/23:59:59",
            "utype": "0",
            "sequence": "1",
            "beginno": str(begin_no),
            "reqcount": str(MAX_PAGE_SIZE),
            "sessionid": str(session_id),
            "RanId": str(secrets.randbelow(90_000_000) + 10_000_000),
        }
        try:
            response = get(
                f"{base_url}{path}", params=params, timeout=(3, 8), allow_redirects=False,
                auth=auth,
            )
        except requests.RequestException as exc:
            raise ConnectionError("Không kết nối được FaceGate qua relay VPS.") from exc
        if int(getattr(response, "status_code", 0)) != 200:
            raise ConnectionError("FaceGate không chấp nhận truy vấn Control Log.")
        body = str(getattr(response, "text", "") or "")
        if len(body.encode("utf-8", errors="ignore")) > MAX_RESPONSE_BYTES:
            raise ValueError("Phản hồi FaceGate vượt giới hạn an toàn.")
        page = parse_control_log_response(body)
        total_count = page["total_count"] if total_count is None else total_count
        session_id = page["session_id"] or session_id
        for record in page["records"]:
            if record["event_id"] not in seen_ids:
                seen_ids.add(record["event_id"])
                records.append(record)
        received = page["response_count"] or len(page["records"])
        if received > MAX_PAGE_SIZE:
            raise ValueError("FaceGate trả số bản ghi vượt giới hạn mỗi trang.")
        if received <= 0:
            break
        begin_no += received
        if begin_no >= total_count:
            break
      else:
        truncated = total_count is not None and total_count > MAX_RECORDS
    finally:
      _close_query_session(base_url, path, auth, "CONTROL", session_id, post)

    return {
        "source": "facegate_control_log",
        "records": records,
        "count": len(records),
        "total_count": int(total_count or 0),
        "truncated": truncated,
        "status_semantics_verified": False,
        "attendance_calculation_enabled": False,
    }
