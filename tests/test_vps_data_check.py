from pathlib import Path

from vera_vps_data_check import _running_api_environment


def test_reads_only_allowed_database_environment(tmp_path: Path):
    process = tmp_path / "123"
    process.mkdir()
    (process / "cmdline").write_bytes(b"uvicorn\0vera_web_v2_api_v38:app\0")
    (process / "environ").write_bytes(
        b"DB_HOST=db.example\0DB_USER=vera\0DB_PASS=secret\0UNRELATED=hidden\0"
    )

    assert _running_api_environment(tmp_path) == {
        "DB_HOST": "db.example",
        "DB_USER": "vera",
        "DB_PASS": "secret",
    }


def test_returns_empty_when_api_process_is_absent(tmp_path: Path):
    process = tmp_path / "456"
    process.mkdir()
    (process / "cmdline").write_bytes(b"python\0worker.py\0")
    (process / "environ").write_bytes(b"DB_PASS=must-not-be-read\0")

    assert _running_api_environment(tmp_path) == {}
