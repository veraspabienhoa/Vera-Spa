"""Google credentials shared by Cloud Run, VPS API, and Streamlit."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tomllib
from typing import Iterable

import google.auth
from google.oauth2.service_account import Credentials


def _streamlit_secret_paths() -> list[Path]:
    configured = str(os.getenv("VERA_STREAMLIT_SECRETS_FILE", "") or "").strip()
    candidates = [
        Path(configured).expanduser() if configured else None,
        Path.home() / ".streamlit" / "secrets.toml",
        Path(__file__).resolve().parent / ".streamlit" / "secrets.toml",
    ]
    output: list[Path] = []
    for candidate in candidates:
        if candidate is not None and candidate not in output:
            output.append(candidate)
    return output


def _streamlit_service_account(paths: Iterable[Path] | None = None) -> dict | None:
    for path in paths or _streamlit_secret_paths():
        try:
            with Path(path).open("rb") as handle:
                payload = tomllib.load(handle)
        except FileNotFoundError:
            continue
        account = payload.get("gcp_service_account") if isinstance(payload, dict) else None
        if isinstance(account, dict) and account.get("client_email") and account.get("private_key"):
            return dict(account)
    return None


def google_credentials(scopes: Iterable[str], *, secret_paths: Iterable[Path] | None = None):
    """Resolve credentials in the order available on each deployment target."""
    requested_scopes = list(scopes)
    env_json = str(os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "") or "").strip()
    if env_json:
        return Credentials.from_service_account_info(json.loads(env_json), scopes=requested_scopes)

    account = _streamlit_service_account(secret_paths)
    if account:
        return Credentials.from_service_account_info(account, scopes=requested_scopes)

    credentials, _ = google.auth.default(scopes=requested_scopes)
    return credentials
