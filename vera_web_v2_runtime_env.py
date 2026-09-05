"""Load deployment-managed Web V2 database settings before API imports.

The VPS API is launched by a system service, while deployment is performed by
the same unprivileged account.  A system service does not inherit the user's
manager environment, so the API reads its own private configuration file.
Only the database/Auth allowlist is accepted.
"""
from __future__ import annotations

import os
import pwd
import shlex
import stat
from pathlib import Path


RUNTIME_ENV_RELATIVE_PATH = Path(".config/vera-spa/web-v2-api.env")
RUNTIME_ENV_KEYS = frozenset({
    "VERA_DB_ENABLED",
    "VERA_DATA_BACKEND",
    "DB_HOST",
    "DB_PORT",
    "DB_NAME",
    "DB_USER",
    "DB_PASS",
    "DB_SSLMODE",
    "DB_CONNECT_TIMEOUT",
    "VERA_AUTH_PROVIDER",
})
REQUIRED_RUNTIME_ENV_KEYS = RUNTIME_ENV_KEYS
MAX_RUNTIME_ENV_BYTES = 64 * 1024


def _decode_value(raw_value: str) -> str:
    lexer = shlex.shlex(raw_value, posix=True)
    lexer.whitespace_split = True
    lexer.commenters = ""
    values = list(lexer)
    if len(values) != 1:
        raise ValueError("managed runtime value is malformed")
    value = values[0]
    if any(character in value for character in ("\x00", "\r", "\n")):
        raise ValueError("managed runtime value contains a control character")
    return value


def _validate_settings(settings: dict[str, str]) -> None:
    if set(settings) != REQUIRED_RUNTIME_ENV_KEYS:
        raise ValueError("managed runtime environment is incomplete")
    expected = {
        "VERA_DB_ENABLED": "1",
        "VERA_DATA_BACKEND": "postgres",
        "DB_SSLMODE": "require",
        "VERA_AUTH_PROVIDER": "local",
    }
    if any(settings[key].strip().lower() != value for key, value in expected.items()):
        raise ValueError("managed runtime environment has unsafe mode settings")
    if any(not settings[key] for key in ("DB_HOST", "DB_NAME", "DB_USER", "DB_PASS")):
        raise ValueError("managed runtime database settings are incomplete")
    try:
        port = int(settings["DB_PORT"])
        timeout = int(settings["DB_CONNECT_TIMEOUT"])
    except ValueError as exc:
        raise ValueError("managed runtime numeric setting is malformed") from exc
    if not 1 <= port <= 65535 or not 3 <= timeout <= 120:
        raise ValueError("managed runtime numeric setting is out of range")


def _read_private_file(path: Path) -> str:
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(path, flags)
    try:
        file_stat = os.fstat(fd)
        if not stat.S_ISREG(file_stat.st_mode):
            raise ValueError("managed runtime path is not a regular file")
        if file_stat.st_uid != os.getuid():
            raise PermissionError("managed runtime file has a different owner")
        if stat.S_IMODE(file_stat.st_mode) & 0o077:
            raise PermissionError("managed runtime file permissions are too broad")
        with os.fdopen(fd, "r", encoding="utf-8") as stream:
            fd = -1
            content = stream.read(MAX_RUNTIME_ENV_BYTES + 1)
    finally:
        if fd >= 0:
            os.close(fd)
    if len(content.encode("utf-8")) > MAX_RUNTIME_ENV_BYTES:
        raise ValueError("managed runtime file is too large")
    return content


def load_managed_runtime_environment() -> bool:
    """Atomically apply the complete private DB/Auth environment allowlist."""
    runtime_path = Path(pwd.getpwuid(os.getuid()).pw_dir) / RUNTIME_ENV_RELATIVE_PATH
    try:
        content = _read_private_file(runtime_path)
    except FileNotFoundError:
        return False
    except (OSError, UnicodeError, ValueError) as exc:
        raise RuntimeError("Web V2 managed runtime environment file is unsafe") from exc

    parsed: dict[str, str] = {}
    try:
        for raw_line in content.splitlines():
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            key, separator, raw_value = line.partition("=")
            key = key.strip()
            if not separator or key not in RUNTIME_ENV_KEYS:
                continue
            if key in parsed:
                raise ValueError("managed runtime key is duplicated")
            parsed[key] = _decode_value(raw_value.strip())
        _validate_settings(parsed)
    except ValueError as exc:
        raise RuntimeError("Web V2 managed runtime environment file is invalid") from exc

    previous = {key: os.environ.get(key) for key in parsed}
    try:
        os.environ.update(parsed)
    except (OSError, ValueError):
        for key, value in previous.items():
            if value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = value
        raise RuntimeError("Web V2 managed runtime environment could not be applied")
    print("Web V2 runtime environment: managed PostgreSQL/Auth settings loaded")
    return True
