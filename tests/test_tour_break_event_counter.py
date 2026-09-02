from datetime import date, datetime
from pathlib import Path

from vera_tour_break_counter import next_break_event_state, tour_business_date


def test_new_break_rows_increment_once_not_countif_snapshot():
    first, metrics = next_break_event_state(
        {}, {"2026-09-02|an|18:00": "ca1", "2026-09-02|binh|18:10": "ca2"},
        {"an": "ca1", "binh": "ca2"},
    )
    assert metrics["all"] == {"break_total_count": 2, "break_active_count": 2}

    second, metrics = next_break_event_state(
        first, {"2026-09-02|an|18:00": "ca1", "2026-09-02|binh|18:10": "ca2"},
        {"an": "ca1", "binh": "ca2"},
    )
    assert metrics["all"] == {"break_total_count": 2, "break_active_count": 2}

    third, metrics = next_break_event_state(
        second, {"2026-09-02|an|18:00": "ca1", "2026-09-02|binh|18:10": "ca2"},
        {"binh": "ca2"},
    )
    assert metrics["all"] == {"break_total_count": 2, "break_active_count": 1}

    _, metrics = next_break_event_state(
        third,
        {
            "2026-09-02|an|18:00": "ca1",
            "2026-09-02|binh|18:10": "ca2",
            "2026-09-02|an|21:00": "ca1",
        },
        {"an": "ca1", "binh": "ca2"},
    )
    assert metrics["all"] == {"break_total_count": 3, "break_active_count": 2}


def test_tour_ui_displays_cumulative_dash_active():
    page = (Path(__file__).resolve().parents[1] / "web-v2/src/pages/TourPage.jsx").read_text(encoding="utf-8")
    assert "`${breakTotal}-${breakActive}`" in page
    assert "Tổng lượt-Đang ở ngoài" in page


def test_completed_attendance_break_counts_total_but_not_currently_outside():
    _, metrics = next_break_event_state(
        {}, {"2026-09-02|cam-nhung|18:41:02": "ca1"}, {},
    )
    assert metrics["all"] == {"break_total_count": 1, "break_active_count": 0}


def test_business_date_rolls_over_at_1000_not_midnight():
    assert tour_business_date(datetime(2026, 9, 3, 9, 59, 59)) == date(2026, 9, 2)
    assert tour_business_date(datetime(2026, 9, 3, 10, 0, 0)) == date(2026, 9, 3)
