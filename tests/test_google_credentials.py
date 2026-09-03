import json

import vera_google_credentials as credentials_module


def _service_account_payload():
    return {
        "type": "service_account",
        "project_id": "vera-test",
        "private_key_id": "key-id",
        "private_key": "-----BEGIN PRIVATE KEY-----\ntest\n-----END PRIVATE KEY-----\n",
        "client_email": "vera@example.test",
        "client_id": "123",
        "auth_uri": "https://accounts.google.com/o/oauth2/auth",
        "token_uri": "https://oauth2.googleapis.com/token",
    }


def test_google_credentials_prefers_service_account_json(monkeypatch, tmp_path):
    payload = _service_account_payload()
    captured = []
    monkeypatch.setenv("GOOGLE_SERVICE_ACCOUNT_JSON", json.dumps(payload))
    monkeypatch.setattr(
        credentials_module.Credentials,
        "from_service_account_info",
        lambda info, scopes: captured.append((info, scopes)) or "env-credentials",
    )

    result = credentials_module.google_credentials(["scope-a"], secret_paths=[tmp_path / "missing.toml"])

    assert result == "env-credentials"
    assert captured == [(payload, ["scope-a"])]


def test_google_credentials_reads_existing_streamlit_secret(monkeypatch, tmp_path):
    payload = _service_account_payload()
    secret = tmp_path / "secrets.toml"
    secret.write_text(
        "[gcp_service_account]\n"
        + "\n".join(f"{key} = {json.dumps(value)}" for key, value in payload.items())
        + "\n",
        encoding="utf-8",
    )
    captured = []
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setattr(
        credentials_module.Credentials,
        "from_service_account_info",
        lambda info, scopes: captured.append((info, scopes)) or "streamlit-credentials",
    )

    result = credentials_module.google_credentials(["scope-b"], secret_paths=[secret])

    assert result == "streamlit-credentials"
    assert captured == [(payload, ["scope-b"])]


def test_google_credentials_keeps_adc_fallback(monkeypatch, tmp_path):
    monkeypatch.delenv("GOOGLE_SERVICE_ACCOUNT_JSON", raising=False)
    monkeypatch.setattr(
        credentials_module.google.auth,
        "default",
        lambda scopes: ("adc-credentials", "project"),
    )

    result = credentials_module.google_credentials(["scope-c"], secret_paths=[tmp_path / "missing.toml"])

    assert result == "adc-credentials"
