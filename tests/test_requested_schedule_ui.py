from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_work_schedule_has_all_time_presets_and_custom_date_range():
    source = (ROOT / "web-v2/src/pages/WorkSchedulePage.jsx").read_text(encoding="utf-8")
    for mode, label in (
        ("yesterday", "Hôm qua"),
        ("today", "Hôm nay"),
        ("last_week", "Tuần trước"),
        ("week", "Tuần này"),
        ("next_week", "Tuần sau"),
        ("month", "Tháng này"),
        ("next_month", "Tháng sau"),
        ("custom", "Tùy chỉnh"),
    ):
        assert f"['{mode}', '{label}']" in source

    assert "if (rangeMode === 'yesterday')" in source
    assert "if (rangeMode === 'last_week') return weekDays(base, -1)" in source
    assert "rangeMode === 'custom'" in source
    assert 'aria-label="Từ ngày"' in source
    assert 'aria-label="Đến ngày"' in source


def test_schedule_refetches_when_selected_range_changes():
    source = (ROOT / "web-v2/src/pages/WorkSchedulePage.jsx").read_text(encoding="utf-8")
    assert 'const rangeKey = `${rangeStart}_${rangeEnd}`' in source
    assert "useEffect(() => { void load() }, [department, month, rangeKey])" in source
    assert "start=${rangeStart}&end=${rangeEnd}" in source
