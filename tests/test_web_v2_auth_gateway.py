import hashlib

from fastapi import FastAPI
from fastapi.testclient import TestClient
import pytest

import vera_web_v2_auth_gateway as gateway


@pytest.fixture(autouse=True)
def auth_dependencies(monkeypatch):
    """Keep gateway HTTP tests independent of production DB and identity services."""
    employee = {
        "username": "admin", "full_name": "Admin", "role": "admin",
        "password_value": "secret", "login_locked": False,
        "payload": {"Trạng thái làm việc": "Đang làm việc"},
    }
    calls = {"employees": [], "provisions": [], "links": [], "failed": [], "cleared": []}

    def load_employee(username):
        calls["employees"].append(username)
        return employee if username == "admin" else None

    def provision(**kwargs):
        calls["provisions"].append(kwargs)
        return "auth-user-id"

    def unexpected_io(*args, **kwargs):
        raise AssertionError("Tests must stub external HTTP and PostgreSQL explicitly")

    monkeypatch.setenv("VERA_AUTH_PROVIDER", "supabase")
    monkeypatch.setattr(gateway, "_engine_instance", unexpected_io)
    monkeypatch.setattr(gateway._HTTP, "post", unexpected_io)
    monkeypatch.setattr(gateway._HTTP, "request", unexpected_io)
    monkeypatch.setattr(gateway, "_attempt_state", lambda key: (False, 0))
    monkeypatch.setattr(gateway, "_record_failed_attempt", lambda key: calls["failed"].append(key) or 1)
    monkeypatch.setattr(gateway, "_clear_attempt", lambda key: calls["cleared"].append(key))
    monkeypatch.setattr(gateway.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(gateway, "_load_employee", load_employee)
    monkeypatch.setattr(gateway, "_existing_profile_auth_user_id", lambda username: "auth-user-id")
    monkeypatch.setattr(gateway, "_persist_profile_link", lambda **kwargs: calls["links"].append(kwargs))
    # Keep the real provisioner available for its dedicated stale-user test.
    calls["real_provision"] = gateway._create_or_update_auth_user
    monkeypatch.setattr(gateway, "_create_or_update_auth_user", provision)
    return employee, calls


class _Response:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def test_stale_profile_auth_id_is_recreated(monkeypatch, auth_dependencies):
    calls = []

    def fake_request(method, url, *, headers, json, timeout):
        calls.append((method, url, json))
        if method == "PUT" and url.endswith("/auth/v1/admin/users/stale-user-id"):
            return _Response(404, {"message": "User not found"})
        if method == "GET" and "/auth/v1/admin/users?" in url:
            return _Response(200, {"users": []})
        if method == "POST" and url.endswith("/auth/v1/admin/users"):
            return _Response(201, {"id": "replacement-user-id"})
        raise AssertionError(f"Unexpected request: {method} {url}")

    monkeypatch.setattr(gateway._HTTP, "request", fake_request)
    monkeypatch.setattr(gateway, "_service_role_key", lambda: "service-role-key")

    auth_user_id = auth_dependencies[1]["real_provision"](
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-key",
        auth_user_id="stale-user-id",
        internal_email="vera-user@users.veraspa.local",
        ephemeral_password="temporary-password",
        metadata={"employee_username": "admin"},
    )

    assert auth_user_id == "replacement-user-id"
    assert [call[0] for call in calls] == ["PUT", "POST"]


def _client():
    app = FastAPI()
    gateway.install_auth_gateway(
        app,
        supabase_url="https://project.supabase.co",
        supabase_anon_key="public-anon-key",
    )
    return TestClient(app)


def test_login_is_exchanged_server_side_and_never_returns_bridge_password(monkeypatch, auth_dependencies):
    calls = []

    def fake_post(url, *, headers, json, timeout):
        calls.append((url, headers, json, timeout))
        return _Response(200, {
            "access_token": "access-token",
            "refresh_token": "refresh-token",
            "token_type": "bearer",
            "expires_in": 3600,
            "user": {"id": "user-id", "email": "internal@example.test"},
        })

    monkeypatch.setattr(gateway._HTTP, "post", fake_post)
    response = _client().post("/v2/auth/login", json={"username": " admin ", "password": "secret"})

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.json()["access_token"] == "access-token"
    assert "password" not in response.json()
    dependencies = auth_dependencies[1]
    assert dependencies["employees"] == ["admin"]
    assert len(calls) == len(dependencies["provisions"]) == 1
    provision = dependencies["provisions"][0]
    expected_email = f"vera-{hashlib.sha256(b'admin').hexdigest()[:32]}@users.veraspa.local"
    assert provision["internal_email"] == expected_email
    assert provision["ephemeral_password"] != "secret"
    assert provision["ephemeral_password"] not in response.text
    assert calls[0][0] == "https://project.supabase.co/auth/v1/token?grant_type=password"
    assert calls[0][2] == {"email": expected_email, "password": provision["ephemeral_password"]}
    assert dependencies["links"][0]["auth_user_id"] == "auth-user-id"
    assert len(dependencies["cleared"]) == 1
    assert all(call[1]["apikey"] == "public-anon-key" for call in calls)


def test_invalid_credentials_are_returned_without_a_token_exchange(auth_dependencies):
    response = _client().post("/v2/auth/login", json={"username": "admin", "password": "wrong"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Tên đăng nhập hoặc mật khẩu không đúng."
    calls = auth_dependencies[1]
    assert calls["employees"] == ["admin"]
    assert len(calls["failed"]) == 1
    assert calls["provisions"] == calls["links"] == calls["cleared"] == []


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
        assert url.endswith("/auth/v1/token?grant_type=password")
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


def test_login_and_refresh_seed_the_verified_token_cache(monkeypatch):
    verified = []

    def fake_post(url, *, headers, json, timeout):
        access_token = "refreshed-access" if "refresh_token" in json else "login-access"
        return _Response(200, {
            "access_token": access_token,
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
        verified_token_callback=lambda token, uid: verified.append((token, uid)),
    )
    client = TestClient(app)

    assert client.post("/v2/auth/login", json={"username": "admin", "password": "secret"}).status_code == 200
    assert client.post("/v2/auth/refresh", json={"refresh_token": "refresh-token"}).status_code == 200
    assert verified == [
        ("login-access", "auth-user-id"),
        ("refreshed-access", "auth-user-id"),
    ]
