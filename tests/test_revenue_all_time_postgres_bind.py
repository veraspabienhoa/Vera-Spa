from pathlib import Path


def test_all_time_revenue_query_casts_nullable_postgres_date_binds():
    store = Path("vera_revenue_store.py").read_text(encoding="utf-8")
    assert "CAST(:start_date AS date) IS NULL" in store
    assert "CAST(:end_date AS date) IS NULL" in store
    assert ">= CAST(:start_date AS date)" in store
    assert "<= CAST(:end_date AS date)" in store
