from pathlib import Path


def test_leave_update_commits_postgres_before_optional_google_mirror():
    source = (Path(__file__).resolve().parents[1] / "vera_web_v2_api.py").read_text(encoding="utf-8")
    route = source.split('@app.patch("/v2/leave/records/{record_uid}")', 1)[1].split(
        "def _delete_leave_uids", 1
    )[0]

    commit_at = route.index("tx.commit()")
    google_at = route.index("_google_client().open_by_key")
    assert commit_at < google_at
    assert '"mirror_pending": mirror_pending' in route
    assert "PostgreSQL đã cập nhật; MainData đang chờ đồng bộ lại." in route
    assert "Không sửa được lịch nghỉ an toàn" in route[:google_at]
    assert "if has_main_mirror or rebalanced:" in route
    assert "Bản ghi không có vị trí MainData hợp lệ" not in route
