import unittest

from vera_leave_registration_shared import summarize_leave_days


class ApprovedLeaveStatsTests(unittest.TestCase):
    def test_approved_types_keep_fractional_days(self):
        rows = [dict(leave_type=kind, calculated_days=0.5)
                for kind in ('Leader', 'Được duyệt', 'Phép năm')]
        summary = summarize_leave_days(rows)
        self.assertEqual(summary['paid'], 1.5)
        self.assertEqual(summary['total_leave'], 1.5)

    def test_violation_is_never_unpaid_leave(self):
        rows = [dict(leave_type='Vi phạm', leave_reason=reason, calculated_days=0)
                for reason in ('Qua tour CUỐI TUẦN KHÔNG phép', 'Quên chấm công')]
        summary = summarize_leave_days(rows)
        self.assertEqual(summary['unpaid'], 0)
        self.assertEqual(summary['paid'], 0)

    def test_only_exact_unpaid_type_counts_and_penalty_is_preserved(self):
        rows = [dict(leave_type=kind, leave_reason='KHÔNG phép', penalty=500000 if kind == 'Vi phạm' else 0)
                for kind in ('Vi phạm', '', 'Hỗ trợ', 'Không phép', 'Nhóm Không phép khác')]
        summary = summarize_leave_days(rows)
        self.assertEqual(summary['unpaid'], 1)
        self.assertEqual(summary['total_penalty'], 500000)
