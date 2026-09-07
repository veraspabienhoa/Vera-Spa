import unittest

from vera_leave_registration_shared import summarize_leave_days


class ApprovedLeaveStatsTests(unittest.TestCase):
    def test_approved_types_keep_fractional_days(self):
        rows = [dict(leave_type=kind, calculated_days=0.5)
                for kind in ('Leader', 'Được duyệt', 'Phép năm')]
        summary = summarize_leave_days(rows)
        self.assertEqual(summary['paid'], 1.5)
        self.assertEqual(summary['total_leave'], 1.5)

    def test_violation_requires_unpaid_reason(self):
        rows = [dict(leave_type='Vi phạm', leave_reason=reason, calculated_days=0)
                for reason in ('Qua tour CUỐI TUẦN KHÔNG phép', 'Quên chấm công')]
        summary = summarize_leave_days(rows)
        self.assertEqual(summary['unpaid'], 1)
        self.assertEqual(summary['paid'], 0)
