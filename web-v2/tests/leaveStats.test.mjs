import test from 'node:test'
import assert from 'node:assert/strict'
import { summarizeLeaveRecordDays, displayLeaveType } from '../src/lib/leaveStats.js'

test('approved leave types add actual days including halves', () => {
  const rows = ['Leader', 'Được duyệt', 'Phép năm'].map((leave_type) => ({ leave_type, calculated_days: 0.5 }))
  assert.equal(summarizeLeaveRecordDays(rows).paid, 1.5)
})

test('violations do not count as unpaid leave or change label', () => {
  const reason = 'Qua tour CUỐI TUẦN KHÔNG phép'
  const rows = [reason, 'Quên chấm công'].map((leave_reason) => ({ leave_reason, leave_type: 'Vi phạm', calculated_days: 0 }))
  assert.equal(summarizeLeaveRecordDays(rows).unpaid, 0)
  assert.equal(displayLeaveType('Vi phạm', reason), 'Vi phạm')
  assert.equal(displayLeaveType('Vi phạm', 'Quên chấm công'), 'Vi phạm')
})

test('only exact unpaid type counts and violation penalty remains', () => {
  const rows = ['Vi phạm', '', 'Hỗ trợ', 'Không phép', 'Nhóm Không phép khác'].map(leave_type => ({ leave_type, leave_reason: 'KHÔNG phép', penalty: leave_type === 'Vi phạm' ? 500000 : 0 }))
  const summary = summarizeLeaveRecordDays(rows)
  assert.equal(summary.unpaid, 1)
  assert.equal(summary.total_penalty, 500000)
})
