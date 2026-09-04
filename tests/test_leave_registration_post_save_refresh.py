from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_post_save_refresh_does_not_turn_a_committed_leave_into_failure():
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    assert "const afterSave = options?.afterSave === true" in page
    assert "const refreshed = await load({ afterSave: true })" in page
    assert "if (!afterSave)" in page
    assert "không bấm Ghi lần nữa" in page


def test_leave_page_avoids_parallel_database_burst_after_insert():
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    assert "Promise.all([" not in page
    assert page.index("await veraApi.leaveDailyStats") < page.index("await veraApi.leaveRecords")
    assert page.index("await veraApi.leaveRecords") < page.index("await veraApi.leaveReasons")
    assert page.index("await veraApi.leaveReasons") < page.index("await veraApi.employees")
