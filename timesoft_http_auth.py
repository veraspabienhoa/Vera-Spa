"""Browserless TimeSoft authentication for attendance sync.

TimeSoft validates the login form with POST /User/ValidateUser. Using that
first avoids making attendance availability depend on Chromium shared libraries
on the VPS. The existing Playwright login remains a compatibility fallback for
unexpected protocol changes, but an explicit invalid-credential response is
never retried in a browser with the same credentials.

Production VPS credentials may be supplied through a private runtime JSON file
written by the manual Deploy VPS Production workflow. This avoids storing the
TimeSoft username/password in source code or requiring write access to the
root-owned systemd EnvironmentFile.
"""
from __future__ import annotations

import json
import os
import stat
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

import requests


RELEASE = "timesoft-http-auth-2026-09-07-v2-runtime-file"
LOGIN_PATH = "/User/ValidateUser"
INVALID_CREDENTIAL_CODES = {"US0006"}
DEFAULT_RUNTIME_CREDENTIAL_FILE = "/opt/vera-spa/timesoft-credentials.json"


class TimeSoftAuthenticationError(RuntimeError):
    """TimeSoft explicitly rejected the configured account credentials."""


def _truthy(value: Any, default: bool = True) -> bool:
    raw = str(value or "").strip().lower()
    if not raw:
        return default
    return raw not in {"0", "false", "no", "off"}


def _safe_text(ts, value: Any, limit: int = 500) -> str:
    text = " ".join(str(value or "").replace("\r", " ").replace("\n", " ").split())
    for secret in (getattr(ts, "USERNAME", ""), getattr(ts, "PASSWORD", "")):
        secret = str(secret or "")
        if secret:
            text = text.replace(secret, "***")
    return text[:limit]


def _is_true(value: Any) -> bool:
    if value is True:
        return True
    return str(value or "").strip().lower() in {"1", "true", "yes", "ok"}


def refresh_runtime_credentials(ts) -> tuple[str, str]:
    """Refresh ts.USERNAME/PASSWORD from the private VPS runtime file when present.

    The file is intentionally outside the Git checkout. It must be a regular
    file and must not be readable by other users. If the file does not exist,
    the existing environment-backed values remain available for compatibility.
    """
    path = Path(
        str(os.getenv("TIMESOFT_RUNTIME_CREDENTIAL_FILE", DEFAULT_RUNTIME_CREDENTIAL_FILE) or DEFAULT_RUNTIME_CREDENTIAL_FILE)
    )
    try:
        file_stat = path.stat()
    except FileNotFoundError:
        return (
            str(getattr(ts, "USERNAME", "") or "").strip(),
            str(getattr(ts, "PASSWORD", "") or ""),
        )
    except OSError as exc:
        raise RuntimeError("Không đọc được file credential TimeSoft trên VPS.") from exc

    if not stat.S_ISREG(file_stat.st_mode):
        raise RuntimeError("File credential TimeSoft trên VPS không hợp lệ.")
    if stat.S_IMODE(file_stat.st_mode) & 0o007:
        raise RuntimeError("File credential TimeSoft trên VPS đang cho phép user khác đọc; yêu cầu chmod 640/600.")

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError("File credential TimeSoft trên VPS không phải JSON hợp lệ.") from exc
    if not isinstance(payload, dict):
        raise RuntimeError("File credential TimeSoft trên VPS có cấu trúc không hợp lệ.")

    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        raise TimeSoftAuthenticationError("File credential TimeSoft trên VPS đang thiếu username hoặc password.")

    ts.USERNAME = username
    ts.PASSWORD = password
    ts._timesoft_runtime_credentials_source = str(path)
    return username, password


def create_http_authenticated_session(ts) -> requests.Session:
    username, password = refresh_runtime_credentials(ts)
    if not username or not password:
        raise TimeSoftAuthenticationError("Thiếu TIMESOFT_USERNAME/TIMESOFT_PASSWORD trên máy chủ VERA.")

    base_url = str(getattr(ts, "BASE_URL", "") or "").rstrip("/")
    if not base_url:
        raise RuntimeError("TIMESOFT_BASE_URL chưa được cấu hình.")

    report_path = str(getattr(ts, "REPORT_CHECKIN_PAGE", "/Report/ReportEmployeeCheckin/Index"))
    report_url = urljoin(base_url + "/", report_path.lstrip("/"))
    login_url = urljoin(base_url + "/", LOGIN_PATH.lstrip("/"))

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140 Safari/537.36"
        ),
        "Accept-Language": "vi-VN,vi;q=0.9,en;q=0.8",
    })

    # Establish the same initial cookies as a normal browser visit.
    login_page = session.get(report_url, timeout=25, allow_redirects=True)
    login_page.raise_for_status()

    response = session.post(
        login_url,
        data={"userName": username, "password": password, "sendOne": ""},
        headers={
            "Accept": "application/json, text/javascript, */*; q=0.01",
            "X-Requested-With": "XMLHttpRequest",
            "Referer": str(login_page.url),
            "Origin": base_url,
        },
        timeout=25,
        allow_redirects=False,
    )
    response.raise_for_status()
    try:
        payload = response.json()
    except Exception as exc:
        raise RuntimeError(
            "TimeSoft /User/ValidateUser không trả JSON; giao thức đăng nhập có thể đã thay đổi."
        ) from exc
    if not isinstance(payload, dict):
        raise RuntimeError("TimeSoft /User/ValidateUser trả dữ liệu đăng nhập không hợp lệ.")

    valid = _is_true(payload.get("valid"))
    code = str(payload.get("ErrorCode") or "").strip()
    message = _safe_text(ts, payload.get("Message") or "")
    if not valid:
        suffix = f" ({code})" if code else ""
        detail = message or "TimeSoft từ chối đăng nhập."
        if code in INVALID_CREDENTIAL_CODES or "mật khẩu" in detail.lower() or "dang nhap" in detail.lower():
            raise TimeSoftAuthenticationError(
                f"TimeSoft từ chối tài khoản/mật khẩu đang cấu hình{suffix}: {detail}"
            )
        raise TimeSoftAuthenticationError(f"TimeSoft chưa cho phép đăng nhập{suffix}: {detail}")

    # A valid JSON response is not enough: verify that the report no longer
    # redirects back to /User/Login before handing the session to SearchElastic.
    verify = session.get(report_url, timeout=25, allow_redirects=False)
    location = str(verify.headers.get("location") or "")
    if verify.status_code in {301, 302, 303, 307, 308} and "/user/login" in location.lower():
        raise RuntimeError("TimeSoft báo đăng nhập thành công nhưng session vẫn quay lại trang Login.")
    if verify.status_code >= 400:
        verify.raise_for_status()

    setattr(session, "_vera_timesoft_auth_mode", "http-validate-user")
    setattr(session, "_vera_timesoft_auth_release", RELEASE)
    return session


def install(ts) -> None:
    """Patch ts.create_authenticated_session with HTTP-first authentication."""
    if getattr(ts, "_timesoft_http_auth_release", "") == RELEASE:
        return

    original_create_session = ts.create_authenticated_session
    http_enabled = _truthy(os.getenv("TIMESOFT_HTTP_AUTH", "1"), True)

    def create_authenticated_session():
        if not http_enabled:
            refresh_runtime_credentials(ts)
            return original_create_session()
        try:
            session = create_http_authenticated_session(ts)
            log = getattr(ts, "_log", None)
            if callable(log):
                log(f"TIMESOFT AUTH: HTTP /User/ValidateUser OK ({RELEASE})")
            return session
        except TimeSoftAuthenticationError:
            # Do not retry the same rejected credentials through Playwright.
            raise
        except Exception as http_error:
            log = getattr(ts, "_log", None)
            if callable(log):
                log(
                    "TIMESOFT AUTH HTTP WARN: "
                    f"{type(http_error).__name__}: {_safe_text(ts, http_error)}; thử Playwright fallback"
                )
            try:
                # Refresh again immediately before browser fallback so both
                # authentication modes use the same current runtime credentials.
                refresh_runtime_credentials(ts)
                session = original_create_session()
                setattr(session, "_vera_timesoft_auth_mode", "playwright-fallback")
                setattr(session, "_vera_timesoft_auth_release", RELEASE)
                return session
            except Exception as browser_error:
                raise RuntimeError(
                    "Không tạo được session TimeSoft. "
                    f"HTTP={type(http_error).__name__}: {_safe_text(ts, http_error)}; "
                    f"Playwright={type(browser_error).__name__}: {_safe_text(ts, browser_error)}"
                ) from browser_error

    ts.create_authenticated_session = create_authenticated_session
    ts._timesoft_http_auth_release = RELEASE
    ts._timesoft_http_auth_original = original_create_session
