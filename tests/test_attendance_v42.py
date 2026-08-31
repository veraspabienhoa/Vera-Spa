from datetime import date, datetime
import unittest

from vera_attendance_rules import apply_break_restriction, departure_status_is_final


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


if __name__ == "__main__":
    unittest.main()
