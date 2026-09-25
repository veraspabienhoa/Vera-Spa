from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_post_save_refresh_does_not_turn_a_committed_leave_into_failure():
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    assert "const afterSave = options?.afterSave === true" in page
    assert "const refreshed = await latestLoad.current({ afterSave: true })" in page
    assert "if (!afterSave)" in page
    assert "không bấm Ghi lần nữa" in page


def test_leave_page_avoids_parallel_database_burst_after_insert():
    page = (ROOT / "web-v2/src/pages/LeaveRegistrationPage.jsx").read_text(encoding="utf-8")

    # The four leave data sources are serialized by the page loader. An
    # unrelated Promise.all for watch-date notification settings is safe.
    assert "return pageLoader.current.run(jobs" in page
    assert "Promise.all(jobs" not in page
    assert page.index("id: 'records'") < page.index("id: 'daily'") < page.index("id: 'reasons'") < page.index("id: 'employees'")
    # Verify serialization, cancellation and superseded reads by behavior.
    result = subprocess.run(["node", "--test", "tests/leavePageLoader.test.mjs"],
                            cwd=ROOT / "web-v2", capture_output=True, text=True, timeout=20)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "options?.onlyChanged === true && !afterSave" in page
