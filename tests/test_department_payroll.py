from datetime import date

from vera_web_v2_department_payroll import (
    CALCULATION_MODES,
    DEFAULT_CONFIG,
    DEFAULT_EMAIL_TEMPLATE,
    _attendance_totals,
    _clean_config,
    _recalculate,
    _render_template,
)


def _norm(value):
    return str(value or "").strip().casefold()


def test_locker_hourly_formula_matches_attached_macro_rates():
    row = _recalculate({
        "hours_ca1": 8,
        "hours_ca2_before_22": 4.5,
        "hours_ca2_after_22": 3.5,
        "full_allowance": 30000,
        "attendance_bonus": 500000,
        "responsibility": 1000000,
        "seniority": 100000,
        "combo_sales": 0,
        "other_income_1": 0,
        "other_income_2": 0,
        "violation_penalty": 50000,
        "late_penalty": 100000,
        "advance": 2000000,
    }, DEFAULT_CONFIG["locker"])

    assert row["salary"] == 8 * 27000 + 4.5 * 27000 + 3.5 * 30000
    assert row["total_salary"] == row["salary"] + 30000 + 500000 + 1000000 + 100000
    assert row["net_salary"] == row["total_salary"] - 50000 - 100000 - 2000000


def test_letan_is_hourly_with_30000_before_22_and_33000_after_22():
    row = _recalculate({
        "hours_ca1": 8,
        "hours_ca2_before_22": 4.5,
        "hours_ca2_after_22": 3.5,
    }, DEFAULT_CONFIG["letan"])

    assert DEFAULT_CONFIG["letan"]["calculation_mode"] == "hourly"
    assert row["salary"] == 8 * 27000 + 4.5 * 30000 + 3.5 * 33000


def test_quanly_locker_and_letan_are_locked_to_hourly_calculation():
    assert CALCULATION_MODES["quanly"] == "hourly"
    assert CALCULATION_MODES["locker"] == "hourly"
    assert CALCULATION_MODES["letan"] == "hourly"
    assert _clean_config("quanly", {"calculation_mode": "monthly"})["calculation_mode"] == "hourly"


def test_tapvu_uses_base_salary_prorated_over_26_work_days():
    config = _clean_config("tapvu", {
        "calculation_mode": "hourly",
        "default_base_salary": 7_800_000,
        "standard_month_days": 20,
    })
    row = _recalculate({"base_salary": 7_800_000, "work_days": 13}, config)

    assert config["calculation_mode"] == "monthly"
    assert config["standard_month_days"] == 26
    assert row["salary"] == 3_900_000


def test_ca2_is_split_at_2200_and_overnight_is_supported():
    totals = _attendance_totals([{
        "date": "03/09/2026",
        "employee_name": "Locker A",
        "shift": "Ca 2",
        "check_in": "17:30:00",
        "check_out": "01:30:00",
        "total_minutes": 480,
    }], "Locker A", _norm, DEFAULT_CONFIG["locker"])

    assert totals["minutes_ca2_before_22"] == 270
    assert totals["minutes_ca2_after_22"] == 210


def test_email_template_contains_department_totals_and_employee():
    subject, body, html = _render_template(DEFAULT_EMAIL_TEMPLATE, {
        "employee_name": "Lê Cảnh Phong",
        "department_label": "Locker",
        "total_salary": 7022000,
        "violation_penalty": 50000,
        "late_penalty": 0,
        "net_salary": 6972000,
    }, "07/2026")

    assert "Lê Cảnh Phong" in subject
    assert "Locker" in subject
    assert "7.022.000đ" in body
    assert "6.972.000đ" in body
    assert "<!doctype html>" in html
