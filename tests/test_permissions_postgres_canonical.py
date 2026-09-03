from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_permission_save_commits_postgres_before_optional_google_mirror():
    source = (ROOT / "vera_web_v2_permissions.py").read_text(encoding="utf-8")

    commit = source.index("tx.commit()")
    mirror = source.index("sheet = google_client().open_by_key", commit)
    assert commit < mirror
    assert "PostgreSQL is the canonical permission store" in source
    assert '"mirror_pending": bool(mirror_warning)' in source
    assert '"warnings": [mirror_warning] if mirror_warning else []' in source


def test_google_mirror_failure_does_not_rollback_saved_permissions():
    source = (ROOT / "vera_web_v2_permissions.py").read_text(encoding="utf-8")
    mirror_block = source.split("# PostgreSQL is the canonical permission store", 1)[1]

    assert "except Exception as mirror_exc:" in mirror_block
    assert "Đã lưu PostgreSQL; chưa đồng bộ được bản sao Google Sheets" in mirror_block
    assert "tx.rollback()" not in mirror_block.split("except HTTPException:", 1)[0]
