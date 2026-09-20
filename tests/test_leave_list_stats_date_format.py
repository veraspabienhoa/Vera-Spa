from pathlib import Path


def test_leave_list_statistics_reads_system_date_format():
    source = Path("web-v2/src/pages/LeaveListPersonalStats.jsx").read_text(encoding="utf-8")

    assert r"(\d{2})[/-](\d{2})[/-](\d{4})" in source
    assert r"(\d{2}[/-]\d{2}[/-]\d{4})" in source
    assert "veraApi.leaveListStats(context.start, context.end, context.employee)" in source
