from pathlib import Path


def test_leave_list_statistics_uses_iso_filters_and_formats_visible_dates():
    source = Path("web-v2/src/pages/LeaveListPersonalStats.jsx").read_text(encoding="utf-8")

    assert 'panel.dataset.leaveStart' in source and 'panel.dataset.leaveEnd' in source
    assert 'formatVeraDate(start)' in source and 'formatVeraDate(end)' in source
    assert "querySelector('.panel-title-row p')" not in source
    assert "veraApi.leaveListStats(context.start, context.end, context.employee)" in source
