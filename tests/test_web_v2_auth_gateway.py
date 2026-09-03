from fastapi import FastAPI
from fastapi.testclient import TestClient

import vera_web_v2_auth_gateway as gateway


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _client():
    app = FastAPI()
    gateway.install_auth_gateway(
        app,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-anon-key",
    )
    return TestClient(app)


def test_login_is_exchanged_server_side_and_never_returns_bridge_password(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        if "/functions/v1/vera-v2-login" in url:
            return _Response(200, {"email": "internal@example.test", "password": "ephemeral-secret"})
        return _Response(200, {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {"id": "user-id", "email": "internal@example.test"},
        })

    monkeypatch.setattr(gateway._HTTP, "post", fake_post)
    response = _client().post("/v2/auth/login", json={"username": " admin ", "password": "vera-password"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.json()["access_token"] == "access-token"
    assert "password" not in response.json()
    assert calls[0][2] == {"username": "admin", "password": "vera-password"}
    assert calls[1][2] == {"email": "internal@example.test", "password": "ephemeral-secret"}
    assert all(call[1]["apikey"] == "public-anon-key" for call in calls)


def test_invalid_credentials_are_returned_without_a_token_exchange(monkeypatch):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append(url)
        return _Response(401, {"message": "Tên đăng nhập hoặc mật khẩu không đúng."})

    monkeypatch.setattr(gateway._HTTP, "post", fake_post)
    response = _client().post("/v2/auth/login", json={"username": "admin", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Tên đăng nhập hoặc mật khẩu không đúng."
    assert calls == ["https://project.supabase.co/functions/v1/vera-v2-login"]


def test_refresh_token_is_exchanged_by_the_api(monkeypatch):
    def fake_post(url, *, headers, json, timeout):
        assert url.endswith("/auth/v1/token?grant_type=refresh_token")
        assert json == {"refresh_token": "old-refresh-token"}
        return _Response(200, {
            "access_token": "new-access-token",
            "refresh_token": "new-refresh-token",
            "expires_in": 3600,
            "user": {"id": "user-id"},
        })

    monkeypatch.setattr(gateway._HTTP, "post", fake_post)
    response = _client().post("/v2/auth/refresh", json={"refresh_token": "old-refresh-token"})

    assert response.status_code == 200
    assert response.json()["access_token"] == "new-access-token"
    assert response.json()["refresh_token"] == "new-refresh-token"


def test_login_can_include_the_already_verified_vera_profile(monkeypatch):
    def fake_post(url, *, headers, json, timeout):
        if "/functions/v1/vera-v2-login" in url:
            return _Response(200, {
                "email": "internal@example.test",
                "password": "ephemeral-secret",
                "employee_username": "admin",
            })
        return _Response(200, {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "expires_in": 3600,
            "user": {"id": "auth-user-id"},
        })

    monkeypatch.setattr(gateway._HTTP, "post", fake_post)
    app = FastAPI()
    gateway.install_auth_gateway(
        app,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-anon-key",
        profile_loader=lambda username: {
            "employee_username": username,
            "role": "admin",
            "permissions": {"leave": True},
        },
    )

    response = TestClient(app).post("/v2/auth/login", json={"username": "admin", "password": "secret"})

    assert response.status_code == 200
    assert response.json()["vera_profile"]["employee_username"] == "admin"
    assert response.json()["vera_profile"]["auth_user_id"] == "auth-user-id"
