from datetime import date, datetime
import unittest

import vera_auto_check as auto_check
from vera_web_v2_attendance_v42 import _looks_like_final_checkout, _work_day_for_row

from vera_attendance_rules import (
    apply_break_restriction,
    departure_status_is_final,
    late_penalty_eligible,
    supported_late_minutes,
)
from vera_web_v2_snapshot import _apply_support_shift_start, _norm


class DepartureStatusFinalTests(unittest.TestCase):
    def setUp(self):
        self.work_day = date(2026, 8, 31)

    def test_lone_morning_checkin_is_not_a_departure(self):
        self.assertFalse(
            departure_status_is_final(
                clustered_punch_count=1,
                work_day=self.work_day,
                expected_end=datetime(2026, 8, 31, 23, 0),
                now=datetime(2026, 8, 31, 11, 0),
            )
        )

    def test_active_shift_does_not_trust_temporary_departure_status(self):
        self.assertFalse(
            departure_status_is_final(
                clustered_punch_count=2,
                work_day=self.work_day,
                expected_end=datetime(2026, 8, 31, 23, 0),
                now=datetime(2026, 8, 31, 20, 0),
            )
        )

    def test_completed_shift_with_multiple_punches_can_use_departure_status(self):
        self.assertTrue(
            departure_status_is_final(
                clustered_punch_count=2,
                work_day=self.work_day,
                expected_end=datetime(2026, 8, 31, 23, 0),
                now=datetime(2026, 8, 31, 23, 30),
            )
        )

    def test_restriction_does_not_overwrite_configured_break(self):
        cfg = {
            "break_enabled": True,
            "break_planned_minutes": 90,
            "faceid_cluster_minutes": 10,
        }

        restricted = apply_break_restriction(cfg, ["đi trễ"])

        self.assertTrue(restricted["break_enabled"])
        self.assertEqual(restricted["break_planned_minutes"], 90)
        self.assertEqual(restricted["break_restricted_reason"], "đi trễ")


class SupportedShiftStartTests(unittest.TestCase):
    def setUp(self):
        self.reason = "Hỗ trợ Ca 1 đi trễ 2 tiếng"
        self.allowances = {(date(2026, 8, 31), _norm("Nhân viên A")): (120, self.reason)}

    def test_checkin_before_supported_start_is_on_time(self):
        item = {
            "date": "31/08/2026",
            "employee_name": "Nhân viên A",
            "shift_start": "10:00",
            "check_in": "31/08/2026 10:24:06",
            "late_minutes": 24,
            "arrival_status": "Đi trễ",
        }

        adjusted = _apply_support_shift_start(item, self.allowances)

        self.assertEqual(adjusted["shift_start"], "12:00")
        self.assertEqual(adjusted["late_minutes"], 0)
        self.assertEqual(adjusted["arrival_status"], "Đúng giờ")

    def test_checkin_after_supported_start_uses_new_late_minutes(self):
        item = {
            "date": "31/08/2026",
            "employee_name": "Nhân viên A",
            "shift_start": "10:00",
            "check_in": "31/08/2026 12:02:31",
            "late_minutes": 122,
            "arrival_status": "Đi trễ",
        }

        adjusted = _apply_support_shift_start(item, self.allowances)

        self.assertEqual(adjusted["shift_start"], "12:00")
        self.assertEqual(adjusted["late_minutes"], 2)
        self.assertEqual(adjusted["arrival_status"], "Đi trễ")


class OvernightCheckoutBoundaryTests(unittest.TestCase):
    def setUp(self):
        self.work_day = date(2026, 9, 3)

    def test_23_to_03_is_always_checkout(self):
        item = {}
        for value in (
            datetime(2026, 9, 3, 23, 0),
            datetime(2026, 9, 4, 0, 30),
            datetime(2026, 9, 4, 3, 0),
        ):
            self.assertTrue(_looks_like_final_checkout(value, self.work_day, item, 2))

    def test_after_03_is_not_forced_to_previous_day_checkout(self):
        value = datetime(2026, 9, 4, 3, 1)
        self.assertFalse(_looks_like_final_checkout(value, self.work_day, {}, 2))
        self.assertEqual(_work_day_for_row({}, [value]), date(2026, 9, 4))

    def test_03_exactly_belongs_to_previous_workday(self):
        self.assertEqual(
            _work_day_for_row({}, [datetime(2026, 9, 4, 3, 0)]),
            date(2026, 9, 3),
        )


class SupportedLatePenaltyThresholdTests(unittest.TestCase):
    def test_support_is_subtracted_before_five_minute_threshold(self):
        self.assertEqual(supported_late_minutes(122, 120), 2)
        self.assertFalse(late_penalty_eligible(122, 5, 120))

    def test_exactly_five_minutes_after_support_is_penalized(self):
        self.assertEqual(supported_late_minutes(125, 120), 5)
        self.assertTrue(late_penalty_eligible(125, 5, 120))

    def test_unknown_support_is_fail_closed(self):
        self.assertIsNone(supported_late_minutes(200, None))
        self.assertFalse(late_penalty_eligible(200, 5, None))

    def test_arrival_and_return_rules_keep_four_minute_grace(self):
        reasons = (
            "Đi trễ không phép",
            "Đi trễ nhỏ hơn hoặc bằng 30 phút",
            "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút",
            "Vào lại trễ",
        )
        for reason in reasons:
            for minute in range(1, 5):
                self.assertFalse(auto_check.automatic_late_penalty_eligible(reason, minute))
            self.assertTrue(auto_check.automatic_late_penalty_eligible(reason, 5))

    def test_shared_writer_refuses_four_minute_penalty_before_database_write(self):
        ok, message = auto_check.save_violation(
            None,
            work_date=date(2026, 9, 3),
            employee="Minh Anh",
            reason_item={"name": "Ra ngoài vào muộn nhỏ hơn hoặc bằng 30 phút"},
            detail="Vào lại trễ 3 phút",
            source="test",
            minutes=3,
        )

        self.assertTrue(ok)
        self.assertEqual(message, "SKIP_GRACE_PERIOD")


if __name__ == "__main__":
    unittest.main()


def test_grace_cleanup_retains_new_subminute_arrival_fine(monkeypatch):
    from types import SimpleNamespace
    statements = []
    rows = [dict(id=1, reason='Đi trễ không phép', minutes=34/60, leave_record_uid='arrival'),
            dict(id=2, reason='Ra ngoài vào muộn', minutes=3, leave_record_uid='return')]
    class Connection:
        def execute(self, sql, params=None):
            statements.append((str(sql), params))
            return SimpleNamespace(mappings=lambda: SimpleNamespace(all=lambda: rows))
    monkeypatch.setattr(auto_check, 'ensure_schema', lambda _: None)
    assert auto_check.revoke_grace_period_penalties(Connection()) == 1
    mutations = [params for sql, params in statements if sql.lstrip().startswith(('DELETE', 'UPDATE'))]
    assert mutations == [{'uid': 'return'}, {'id': 2}]


def test_immediate_arrival_rejects_zero_negative_and_nonfinite_minutes():
    for value in [0, -1, float('nan'), float('inf'), 'invalid', None]:
        assert not auto_check.automatic_late_penalty_eligible('Đi trễ không phép', value)
    assert not auto_check.automatic_late_penalty_eligible('Đi trễ không phép', 1/60)
