"""Scheduled wages exclude verified lateness independently of penalty creation."""
import pytest

from test_department_payroll_employee_sources import (
    DEFINITIONS, config, dep, event, norm, payroll_row, record, schedule, mixed,
)


def calculate(actual, events=(), fine=0, mode='hourly'):
    cfg = config(mode=mode)
    planned = [schedule()]
    totals = dep._schedule_totals(planned, 'a', 'letan', DEFINITIONS, cfg, norm)
    return dep._late_payroll_adjustment(
        payroll_row(totals, cfg, 'schedule', fine), cfg, 'schedule', events,
        actual, planned, DEFINITIONS, norm)


def verified(**kwargs):
    return record(identity_verified=True, attendance_pending_reasons=[], **kwargs)


@pytest.mark.parametrize('mode,expected', [('hourly', 209250), ('monthly', 290625)])
def test_late_without_penalty_is_unpaid_even_without_checkout(mode, expected):
    row = calculate([verified(departure='')], mode=mode)
    assert row['hours_ca1'] == 7.75
    assert row['salary'] == expected
    assert row['net_salary'] == expected
    assert row['effective_late_penalty'] == 0
    assert row['unpaid_late_minutes'] == 15


@pytest.mark.parametrize('approved', [True, False])
def test_linked_fine_does_not_deduct_arrival_twice(approved):
    late = event(config(), approved)
    row = calculate([verified()], [late], late['amount'])
    assert row['hours_ca1'] == 7.75
    assert row['unpaid_late_wage'] == 6750
    assert row['net_salary'] == 209250 - (0 if approved else 6750)
    assert len(row['late_penalty_adjustments']) == 1


def test_manual_fine_keeps_its_amount_separate_from_unpaid_time():
    row = calculate([verified()], fine=10000)
    assert row['salary'] == 209250
    assert row['net_salary'] == 199250


def test_schedule_without_scans_does_not_become_attendance_pay():
    row = calculate([])
    assert row['salary'] == 216000
    assert not row.get('configuration_pending')


def test_unverified_known_lateness_cannot_silently_receive_full_pay():
    row = calculate([record()])
    assert row['configuration_pending']
    assert row['salary'] is None


def test_schedule_only_calculation_loads_arrivals_once_without_fine(mixed):
    mixed['configs']['b'] = config()
    mixed['records'] = [verified(), verified(name='b', arrival='09:00')]
    rows = dep._combined_calculation(mixed['conn'], '2026-10', norm)['rows']
    assert rows[0]['salary'] == 209250
    assert rows[1]['salary'] == 216000
    assert mixed['attendance_reads'] == mixed['schedule_reads'] == 1


def test_save_rechecks_wage_exclusion_and_does_not_deduct_twice(mixed):
    mixed['records'] = [verified(), verified(name='b', arrival='09:00')]
    rows = dep._combined_calculation(mixed['conn'], '2026-10', norm)['rows']
    clean = dep._clean_combined_rows(mixed['conn'], rows, norm, month='2026-10')
    assert clean[0]['hours_ca1'] == 7.75
    assert clean[0]['salary'] == 209250
    mixed['records'][0]['check_in'] = '09:30'
    with pytest.raises(dep.HTTPException) as error:
        dep._clean_combined_rows(mixed['conn'], rows, norm, month='2026-10')
    assert error.value.status_code == 409


def test_closed_historical_archive_does_not_require_live_cache_freshness():
    actual = verified(attendance_fine_evidence_ready=False,
                      attendance_fine_evidence_reasons=['stale_archive'])
    assert calculate([actual])['salary'] == 209250


def test_incomplete_archive_still_blocks_known_lateness():
    actual = verified()
    actual['attendance_pending_reasons'] = ['incomplete_archive']
    assert calculate([actual])['configuration_pending']
