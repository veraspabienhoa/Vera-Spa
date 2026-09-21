from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_post_save_refresh_does_not_turn_a_committed_leave_into_failure():
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    assert "const afterSave = options?.afterSave === true" in page
    assert "const refreshed = await latestLoad.current({ afterSave: true })" in page
    assert "if (!afterSave)" in page
    assert "không bấm Ghi lần nữa" in page


def test_leave_page_avoids_parallel_database_burst_after_insert():
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")
    loader = (ROOT / "web-v2/src/lib/leavePageLoader.js").read_text(encoding="utf-8")

    # The four leave data sources are serialized by the page loader. An
    # unrelated Promise.all for watch-date notification settings is safe.
    assert "return pageLoader.current.run(jobs" in page
    assert "Promise.all(jobs" not in page
    assert page.index("id: 'records'") < page.index("id: 'daily'") < page.index("id: 'reasons'") < page.index("id: 'employees'")
    assert "const result = tail.then(async () =>" in loader
    assert "const data = await job.read()" in loader
    assert "options?.onlyChanged === true && !afterSave" in page
