"""Server-side Supabase authentication gateway for Web V2.

The browser talks to api.veraspa.vn.  The API then performs the existing VERA
credential bridge and Supabase token exchange server-to-server.  This keeps
login working for clients whose network or in-app browser cannot reach the
Supabase Edge Function directly.
"""
from __future__ import annotations

import time
from typing import Any

import requests
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field


_RETRYABLE_STATUS = {502, 503, 504}
_NO_STORE_HEADERS = {
    "Cache-Control": "no-store, max-age=0",
    "Pragma": "no-cache",
}


class VeraLoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=120)
    password: str = Field(min_length=1, max_length=256)


class VeraRefreshRequest(BaseModel):
    refresh_token: str = Field(min_length=1, max_length=4096)


def _post_with_retry(url: str, *, headers: dict[str, str], payload: dict[str, Any]):
    last_error: requests.RequestException | None = None
    for attempt in range(2):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=(5, 15))
        except requests.RequestException as exc:
            last_error = exc
            if attempt == 0:
                time.sleep(0.35)
                continue
            raise HTTPException(503, "Dịch vụ đăng nhập tạm thời chưa kết nối được.") from exc
        if response.status_code not in _RETRYABLE_STATUS or attempt == 1:
            return response
        time.sleep(0.35)
    raise HTTPException(503, "Dịch vụ đăng nhập tạm thời chưa kết nối được.") from last_error


def _response_json(response) -> dict[str, Any]:
    try:
        payload = response.json()
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _raise_upstream_error(response, *, default_message: str) -> None:
    payload = _response_json(response)
    message = str(
        payload.get("message")
        or payload.get("msg")
        or payload.get("error_description")
        or ""
    ).strip()
    if response.status_code in {400, 401, 403, 429} and message:
        raise HTTPException(response.status_code, message[:300])
    raise HTTPException(503, default_message)


def _public_session(payload: dict[str, Any]) -> dict[str, Any]:
    access_token = str(payload.get("access_token") or "")
    refresh_token = str(payload.get("refresh_token") or "")
    user = payload.get("user")
    if not access_token or not refresh_token or not isinstance(user, dict):
        raise HTTPException(503, "Supabase không trả về phiên đăng nhập hợp lệ.")
    return {
        "access_token": access_token,
        "refresh_token": refresh_token,
        "token_type": str(payload.get("token_type") or "bearer"),
        "expires_in": int(payload.get("expires_in") or 3600),
        "expires_at": int(payload.get("expires_at") or 0),
        "user": user,
    }


def install_auth_gateway(
    app: FastAPI,
    *,
    supabase_url: str,
    supabase_anon_key: str,
) -> None:
    if any(getattr(route, "path", "") == "/v2/auth/login" for route in app.routes):
        return

    def _headers() -> dict[str, str]:
        if not supabase_url or not supabase_anon_key:
            raise HTTPException(503, "API Auth chưa được cấu hình.")
        return {
            "apikey": supabase_anon_key,
            "Authorization": f"Bearer {supabase_anon_key}",
            "Content-Type": "application/json",
        }

    @app.post("/v2/auth/login")
    def login(body: VeraLoginRequest):
        username = body.username.strip()
        if not username:
            raise HTTPException(400, "Tên đăng nhập hoặc mật khẩu không hợp lệ.")

        headers = _headers()
        bridge_response = _post_with_retry(
            f"{supabase_url}/functions/v1/vera-v2-login",
            headers=headers,
            payload={"username": username, "password": body.password},
        )
        if bridge_response.status_code != 200:
            _raise_upstream_error(
                bridge_response,
                default_message="Dịch vụ xác thực VERA tạm thời chưa sẵn sàng.",
            )
        bridge = _response_json(bridge_response)
        internal_email = str(bridge.get("email") or "")
        ephemeral_password = str(bridge.get("password") or "")
        if not internal_email or not ephemeral_password:
            raise HTTPException(503, "Dịch vụ xác thực VERA trả về dữ liệu không hợp lệ.")

        token_response = _post_with_retry(
            f"{supabase_url}/auth/v1/token?grant_type=password",
            headers=headers,
            payload={"email": internal_email, "password": ephemeral_password},
        )
        if token_response.status_code != 200:
            _raise_upstream_error(
                token_response,
                default_message="Chưa tạo được phiên đăng nhập VERA.",
            )
        return JSONResponse(_public_session(_response_json(token_response)), headers=_NO_STORE_HEADERS)

    @app.post("/v2/auth/refresh")
    def refresh(body: VeraRefreshRequest):
        token_response = _post_with_retry(
            f"{supabase_url}/auth/v1/token?grant_type=refresh_token",
            headers=_headers(),
            payload={"refresh_token": body.refresh_token},
        )
        if token_response.status_code != 200:
            _raise_upstream_error(
                token_response,
                default_message="Phiên đăng nhập đã hết hạn. Vui lòng đăng nhập lại.",
            )
        return JSONResponse(_public_session(_response_json(token_response)), headers=_NO_STORE_HEADERS)
