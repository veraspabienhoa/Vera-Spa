"""Synthetic-only coverage of independently granted Live Tour calendar filters."""
from datetime import date, datetime, timezone

import pytest

from vera_live_tour_date_policy import (
    DATE_FEATURES, FINITE_PRESETS, PARENT_FEATURES, PRESETS, SECTIONS, DatePolicyError,
    allowed_ranges, authorize_request, build_policy, calendar_date, canonical_range,
    date_allowed, feature_id, filter_rows, server_today,
)

NOW = datetime(2024, 3, 15, 12, tzinfo=timezone.utc)


def grants_for(section, *presets, **overrides):
    features = {"live_tour_view": True, **{feature: True for feature in PARENT_FEATURES[section]}}
    features.update({feature_id(section, preset): True for preset in presets})
    features.update(overrides)
    return features


def policy_for(section, *presets, now=NOW, **overrides):
    return build_policy(grants_for(section, *presets, **overrides), now)


def assert_error(code, function, *args, **kwargs):
    with pytest.raises(DatePolicyError) as caught:
        function(*args, **kwargs)
    assert caught.value.status_code == code
    assert caught.value.detail


@pytest.mark.parametrize("section", SECTIONS)
def test_capability_contract_includes_exact_independent_feature_ids(section):
    policy = policy_for(section, *PRESETS)
    assert policy == {"version": 1, "server_today": "2024-03-15", "sections": {
        name: list(PRESETS) if name == section else [] for name in SECTIONS
    }}
    assert len(DATE_FEATURES) == len(set(DATE_FEATURES)) == 32
    assert feature_id(section, "last-week") == f"live_tour_{section}_date_last_week"
    assert feature_id(section, "last-month") == f"live_tour_{section}_date_last_month"


@pytest.mark.parametrize("section", SECTIONS)
def test_feature_grants_cannot_bypass_section_read_parents(section):
    assert build_policy({feature_id(section, item): True for item in PRESETS}, NOW)["sections"][section] == []


@pytest.mark.parametrize("section", SECTIONS)
def test_section_exports_and_standalone_reports_do_not_require_board_access(section):
    policy = policy_for(section, *PRESETS, live_tour_view=False)
    assert policy["sections"][section] == list(PRESETS)
    assert authorize_request(policy, section, NOW, preset="today")["date_from"] == "2024-03-15"


@pytest.mark.parametrize("section,missing", [
    ("pending", "live_tour_pending_view"), ("pending", "live_tour_invoice_view"),
    ("invoices", "live_tour_paid_invoice_view"), ("reports", "live_tour_reports_view"),
])
def test_each_required_section_read_gate_must_be_present(section, missing):
    assert policy_for(section, *PRESETS, **{missing: False})["sections"][section] == []


@pytest.mark.parametrize("history,backup,readable", [(False, False, False), (True, False, True), (False, True, True), (True, True, True)])
def test_history_parent_supports_backup_metadata_without_claiming_audit_grants(history, backup, readable):
    policy = policy_for("history", "today", live_tour_history_view=history, live_tour_backup=backup)
    assert policy["sections"]["history"] == (["today"] if readable else [])


@pytest.mark.parametrize("section", SECTIONS)
@pytest.mark.parametrize("preset", PRESETS)
def test_each_preset_is_independently_allowed_and_other_presets_denied(section, preset):
    policy = policy_for(section, preset)
    kwargs = {"date_from": "2020-01-01", "date_to": "2026-12-31"} if preset == "custom" else {}
    result = authorize_request(policy, section, NOW, preset=preset, **kwargs)
    assert result["preset"] == preset and result["section"] == section
    assert policy["sections"][section] == [preset]
    denied = "yesterday" if preset == "today" else "today"
    assert_error(403, authorize_request, policy, section, NOW, preset=denied)


@pytest.mark.parametrize("moment,today", [
    (datetime(2024, 2, 29, 16, 59, 59, tzinfo=timezone.utc), "2024-02-29"),
    (datetime(2024, 2, 29, 17, 0, tzinfo=timezone.utc), "2024-03-01"),
    (datetime(2024, 12, 31, 17, 0, tzinfo=timezone.utc), "2025-01-01"),
    (datetime(2024, 3, 15, 0, 0), "2024-03-15"),
    (date(2024, 3, 15), "2024-03-15"),
])
def test_vietnam_midnight_and_server_today_contract(moment, today):
    assert server_today(moment).isoformat() == today
    assert build_policy({}, moment)["server_today"] == today


@pytest.mark.parametrize("today,preset,first,last", [
    ("2024-03-01", "today", "2024-03-01", "2024-03-01"),
    ("2024-03-01", "yesterday", "2024-02-29", "2024-02-29"),
    ("2023-03-01", "yesterday", "2023-02-28", "2023-02-28"),
    ("2025-01-01", "yesterday", "2024-12-31", "2024-12-31"),
    ("2024-03-11", "week", "2024-03-11", "2024-03-17"),
    ("2024-03-17", "week", "2024-03-11", "2024-03-17"),
    ("2024-03-18", "week", "2024-03-18", "2024-03-24"),
    ("2025-01-01", "week", "2024-12-30", "2025-01-05"),
    ("2024-03-11", "last-week", "2024-03-04", "2024-03-10"),
    ("2024-03-17", "last-week", "2024-03-04", "2024-03-10"),
    ("2024-01-01", "last-week", "2023-12-25", "2023-12-31"),
    ("2024-02-01", "month", "2024-02-01", "2024-02-29"),
    ("2023-02-28", "month", "2023-02-01", "2023-02-28"),
    ("2024-12-31", "month", "2024-12-01", "2024-12-31"),
    ("2024-03-31", "last-month", "2024-02-01", "2024-02-29"),
    ("2023-03-01", "last-month", "2023-02-01", "2023-02-28"),
    ("2025-01-01", "last-month", "2024-12-01", "2024-12-31"),
])
def test_finite_presets_cover_full_calendar_periods(today, preset, first, last):
    now = date.fromisoformat(today)
    assert canonical_range(preset, now) == (date.fromisoformat(first), date.fromisoformat(last))
    result = authorize_request(policy_for("reports", preset, now=now), "reports", now, preset=preset)
    assert (result["date_from"], result["date_to"]) == (first, last)
    assert result["bounds"] == {"date_from": date.fromisoformat(first), "date_to": date.fromisoformat(last)}


def test_server_clock_not_stale_policy_today_is_authoritative():
    policy = policy_for("pending", "today")
    policy["server_today"] = "1900-01-01"
    later = datetime(2024, 3, 15, 17, tzinfo=timezone.utc)
    assert authorize_request(policy, "pending", later, preset="today")["date_from"] == "2024-03-16"
    assert_error(403, authorize_request, policy, "pending", later, preset="today", date_from="2024-03-15")


@pytest.mark.parametrize("allowed,requested", [("month", "today"), ("all", "today"), ("custom", "today"), ("week", "today"), ("month", "all")])
def test_explicit_preset_denial_is_not_overridden_by_broader_grants(allowed, requested):
    assert_error(403, authorize_request, policy_for("invoices", allowed), "invoices", NOW, preset=requested)


@pytest.mark.parametrize("kwargs", [
    {"date_from": "2024-02-29"}, {"date_to": "2024-04-01"},
    {"selected_date": "2024-02-29"},
    {"date_from": "2020-01-01", "date_to": "2024-03-15", "selected_date": "2024-03-15"},
])
def test_finite_preset_rejects_tampered_bounds_even_with_all_grant(kwargs):
    assert_error(403, authorize_request, policy_for("reports", "month", "all"), "reports", NOW, preset="month", **kwargs)


@pytest.mark.parametrize("kwargs,expected", [
    ({"date_from": "2024-03-07"}, ("2024-03-07", "2024-03-31")),
    ({"date_to": "2024-03-16"}, ("2024-03-01", "2024-03-16")),
    ({"date_from": "2024-03-07", "date_to": "2024-03-16"}, ("2024-03-07", "2024-03-16")),
    ({"selected_date": "2024-03-08"}, ("2024-03-08", "2024-03-08")),
    ({"date_from": "2024-03-07", "date_to": "2024-03-16", "selected_date": "2024-03-08"}, ("2024-03-08", "2024-03-08")),
])
def test_finite_preset_can_only_be_narrowed(kwargs, expected):
    result = authorize_request(policy_for("reports", "month"), "reports", NOW, preset="month", **kwargs)
    assert (result["date_from"], result["date_to"]) == expected


@pytest.mark.parametrize("preset", ["all", "custom", "month", ""])
def test_selected_day_must_not_expand_requested_bounds(preset):
    assert_error(403, authorize_request, policy_for("reports", *PRESETS), "reports", NOW,
                 preset=preset, date_from="2024-03-07", date_to="2024-03-10", selected_date="2024-03-15")


def test_missing_preset_complete_range_uses_union_not_one_lucky_endpoint():
    policy = policy_for("pending", "yesterday", "today")
    result = authorize_request(policy, "pending", NOW, date_from="2024-03-14", date_to="2024-03-15")
    assert (result["date_from"], result["date_to"]) == ("2024-03-14", "2024-03-15")
    assert_error(403, authorize_request, policy, "pending", NOW, date_from="2024-03-13", date_to="2024-03-15")


def test_disjoint_grants_do_not_authorize_hidden_gap():
    policy = policy_for("history", "last-month", "today")
    ranges = allowed_ranges(policy, "history", NOW)
    assert ranges == ((date(2024, 2, 1), date(2024, 2, 29)), (date(2024, 3, 15), date(2024, 3, 15)))
    assert_error(403, authorize_request, policy, "history", NOW, date_from="2024-02-01", date_to="2024-03-15")
    assert authorize_request(policy, "history", NOW, date_from="2024-02-02", date_to="2024-02-29")
    assert not date_allowed("2024-03-14", ranges)


def test_adjacent_months_merge_without_iterating_multi_year_days():
    policy = policy_for("invoices", "last-month", "month")
    assert allowed_ranges(policy, "invoices", NOW) == ((date(2024, 2, 1), date(2024, 3, 31)),)
    assert authorize_request(policy, "invoices", NOW, date_from="2024-02-01", date_to="2024-03-31")


@pytest.mark.parametrize("presets", [(), ("custom",), ("today",), tuple(FINITE_PRESETS)])
@pytest.mark.parametrize("kwargs", [{}, {"date_from": "2024-03-15"}, {"date_to": "2024-03-15"}, {"date_from": "2024-03-15", "selected_date": "2024-03-15"}])
def test_omitted_preset_and_incomplete_ranges_cannot_bypass_all(presets, kwargs):
    assert_error(403, authorize_request, policy_for("pending", *presets), "pending", NOW, **kwargs)


def test_selected_day_alone_is_a_complete_bounded_legacy_request():
    result = authorize_request(policy_for("reports", "today"), "reports", NOW, selected_date="2024-03-15")
    assert result["date_from"] == result["date_to"] == "2024-03-15"
    assert_error(403, authorize_request, policy_for("reports", "today"), "reports", NOW, selected_date="2024-03-14")


@pytest.mark.parametrize("preset", ["", "all"])
@pytest.mark.parametrize("kwargs,expected", [
    ({}, ("", "")), ({"date_from": "2020-01-01"}, ("2020-01-01", "")),
    ({"date_to": "2030-01-01"}, ("", "2030-01-01")),
    ({"date_from": "2020-01-01", "date_to": "2030-01-01"}, ("2020-01-01", "2030-01-01")),
    ({"selected_date": "2024-03-15"}, ("2024-03-15", "2024-03-15")),
])
def test_all_allows_unbounded_and_narrowed_requests(preset, kwargs, expected):
    policy = policy_for("invoices", "all")
    result = authorize_request(policy, "invoices", NOW, preset=preset, **kwargs)
    assert (result["date_from"], result["date_to"]) == expected
    assert allowed_ranges(policy, "invoices", NOW) is None


@pytest.mark.parametrize("kwargs", [{}, {"date_from": "2024-03-01"}, {"date_to": "2024-03-15"}, {"selected_date": "2024-03-15"}])
def test_explicit_custom_requires_both_dates_even_with_all(kwargs):
    assert_error(400, authorize_request, policy_for("history", "all", "custom"), "history", NOW, preset="custom", **kwargs)


@pytest.mark.parametrize("first,last", [("2020-01-01", "2030-12-31"), ("0001-01-01", "9999-12-31"), ("2024-02-29", "2024-02-29")])
def test_explicit_custom_accepts_real_ordered_multi_year_ranges(first, last):
    policy = policy_for("history", "custom")
    request = authorize_request(policy, "history", NOW, preset="custom", date_from=first, date_to=last)
    assert (request["date_from"], request["date_to"]) == (first, last)
    assert allowed_ranges(policy, "history", NOW, request=request) == ((date.fromisoformat(first), date.fromisoformat(last)),)


def test_custom_alone_never_authorizes_implicit_bounded_or_public_default():
    policy = policy_for("invoices", "custom")
    assert allowed_ranges(policy, "invoices", NOW) == ()
    assert_error(403, authorize_request, policy, "invoices", NOW, date_from="2024-03-01", date_to="2024-03-15")
    assert filter_rows(policy, "invoices", NOW, [{"day": "2024-03-15"}], lambda row: row["day"]) == []


def test_custom_supplement_is_scoped_to_exact_request_section_and_revalidated():
    features = {**grants_for("reports", "custom", "today"), **grants_for("invoices", "custom", "today")}
    policy = build_policy(features, NOW)
    request = authorize_request(policy, "reports", NOW, preset="custom", date_from="2020-01-01", date_to="2020-01-02")
    assert allowed_ranges(policy, "reports", NOW, request=request) == ((date(2020, 1, 1), date(2020, 1, 2)), (date(2024, 3, 15), date(2024, 3, 15)))
    assert allowed_ranges(policy, "invoices", NOW, request=request) == ((date(2024, 3, 15), date(2024, 3, 15)),)
    assert_error(403, allowed_ranges, policy_for("reports", "today"), "reports", NOW, request=request)
    assert_error(400, allowed_ranges, policy, "reports", NOW, request={**request, "date_from": "invalid"})
    # Never accept a forged bounds object over the validated ISO strings.
    forged = {**request, "bounds": {"date_from": date.min, "date_to": date.max}}
    assert allowed_ranges(policy, "reports", NOW, request=forged) == allowed_ranges(policy, "reports", NOW, request=request)


@pytest.mark.parametrize("bad", ["2024-02-30", "2023-02-29", "2024-13-01", "2024-00-01", "2024-01-00", "0000-01-01", "20240315", "2024-W11-5", "2024-3-15", "15-03-2024", "2024-03-15T00:00:00Z", " 2024-03-15", "2024-03-15 ", "2024-03-15\n", "２０２４-０３-１５", 20240315])
@pytest.mark.parametrize("field", ["date_from", "date_to", "selected_date"])
def test_invalid_request_dates_are_rejected_before_any_read(field, bad):
    assert_error(400, authorize_request, policy_for("reports", "all"), "reports", NOW, preset="all", **{field: bad})


@pytest.mark.parametrize("preset", ["", "all", "custom", "month"])
def test_reversed_dates_are_bad_request(preset):
    assert_error(400, authorize_request, policy_for("pending", *PRESETS), "pending", NOW,
                 preset=preset, date_from="2024-03-20", date_to="2024-03-01")


@pytest.mark.parametrize("preset", ["last_week", "Today", "week ", "unknown", 1, None])
def test_unknown_preset_fails_closed(preset):
    assert_error(400, authorize_request, policy_for("reports", *PRESETS), "reports", NOW, preset=preset)


@pytest.mark.parametrize("policy", [{}, {"version": 2, "sections": {"reports": ["all"]}}, {"version": 1, "sections": None}, {"version": 1, "sections": {"reports": "all"}}])
def test_incomplete_or_unsupported_policy_is_not_unrestricted(policy):
    assert allowed_ranges(policy, "reports", NOW) == ()
    assert_error(403, authorize_request, policy, "reports", NOW)


def test_unknown_section_is_bad_request():
    assert_error(400, authorize_request, policy_for("reports", "all"), "customers", NOW)


@pytest.mark.parametrize("raw,expected", [
    ("2024-03-15", date(2024, 3, 15)),
    (date(2024, 3, 15), date(2024, 3, 15)),
    ("2024-03-14T17:00:00Z", date(2024, 3, 15)),
    ("2024-03-15T16:59:59+00:00", date(2024, 3, 15)),
    ("2024-03-15T17:00:00+00:00", date(2024, 3, 16)),
    ("2024-03-15T00:00:00", date(2024, 3, 15)),
    (datetime(2024, 3, 14, 17, tzinfo=timezone.utc), date(2024, 3, 15)),
    (None, None), ("", None), ("2024-02-30", None), ({}, None),
])
def test_stored_row_dates_preserve_existing_vietnam_calendar_semantics(raw, expected):
    assert calendar_date(raw) == expected


def test_row_filter_uses_union_and_does_not_mutate_source_or_expose_undated_rows():
    rows = [{"id": 1, "day": "2024-03-13"}, {"id": 2, "day": "2024-03-14"},
            {"id": 3, "day": "2024-03-15"}, {"id": 4, "day": "2024-03-16"},
            {"id": 5, "day": "invalid"}, {"id": 6}]
    result = filter_rows(policy_for("pending", "today", "yesterday"), "pending", NOW, iter(rows), lambda row: row.get("day"))
    assert [row["id"] for row in result] == [2, 3]
    assert len(rows) == 6 and result[0] is rows[1]
    assert filter_rows(policy_for("pending", "all"), "pending", NOW, rows, lambda row: row.get("day")) == rows


def test_custom_rows_only_appear_with_explicit_authorized_context():
    policy = policy_for("pending", "custom", "today")
    rows = [{"day": "2020-01-01"}, {"day": "2020-01-03"}, {"day": "2024-03-15"}]
    request = authorize_request(policy, "pending", NOW, preset="custom", date_from="2020-01-01", date_to="2020-01-02")
    assert filter_rows(policy, "pending", NOW, rows, lambda row: row["day"]) == [rows[2]]
    assert filter_rows(policy, "pending", NOW, rows, lambda row: row["day"], request=request) == [rows[0], rows[2]]


def test_runtime_policy_and_permission_catalog_keep_the_same_feature_contract():
    from vera_web_v2_live_tour_permissions import (
        DATE_FILTER_DEPENDENCIES, DATE_FILTER_FEATURES, DATE_FILTER_PARENT_ANY,
        DATE_FILTER_POLICY_VERSION, DATE_FILTER_PRESETS, DATE_FILTER_SECTIONS,
    )
    assert DATE_FILTER_POLICY_VERSION == build_policy({}, NOW)["version"]
    assert set(DATE_FEATURES) == set(DATE_FILTER_FEATURES)
    assert tuple(DATE_FILTER_SECTIONS) == SECTIONS
    assert tuple(value.replace("_", "-") for value in DATE_FILTER_PRESETS) == PRESETS
    for section in SECTIONS:
        for preset in PRESETS:
            key = feature_id(section, preset)
            expected_all = set(() if section == "history" else PARENT_FEATURES[section])
            assert DATE_FILTER_DEPENDENCIES[key] == expected_all
            assert DATE_FILTER_PARENT_ANY.get(key, ()) == (PARENT_FEATURES[section] if section == "history" else ())
