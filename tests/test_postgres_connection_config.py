import importlib
import sys
import types


def _load_module(monkeypatch):
    sqlalchemy = types.ModuleType("sqlalchemy")
    sqlalchemy.create_engine = lambda *args, **kwargs: None
    sqlalchemy.text = lambda value: value
    sqlalchemy_engine = types.ModuleType("sqlalchemy.engine")
    sqlalchemy_engine.Engine = object
    monkeypatch.setitem(sys.modules, "sqlalchemy", sqlalchemy)
    monkeypatch.setitem(sys.modules, "sqlalchemy.engine", sqlalchemy_engine)
    sys.modules.pop("vera_postgres", None)
    return importlib.import_module("vera_postgres")


def test_dev_database_defaults(monkeypatch):
    for key in (
        "DATABASE_URL",
        "DB_USER",
        "DB_PASS",
        "DB_NAME",
        "DB_HOST",
        "DB_PORT",
        "INSTANCE_CONNECTION_NAME",
    ):
        monkeypatch.delenv(key, raising=False)

    module = _load_module(monkeypatch)

    assert module._build_database_url() == (
        "postgresql+psycopg://vera_dev:@160.236.192.51:5432/veraspa"
    )


def test_password_is_url_encoded(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.delenv("INSTANCE_CONNECTION_NAME", raising=False)
    monkeypatch.setenv("DB_PASS", "example@password")

    module = _load_module(monkeypatch)

    assert "example%40password" in module._build_database_url()
    assert "example@password" not in module._build_database_url()
