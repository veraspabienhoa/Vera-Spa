import test from 'node:test'
import assert from 'node:assert/strict'
import { summarizeLeaveRecordDays, displayLeaveType } from '../src/lib/leaveStats.js'

test('approved leave types add actual days including halves', () => {
  const rows = ['Leader', 'Được duyệt', 'Phép năm'].map((leave_type) => ({ leave_type, calculated_days: 0.5 }))
  assert.equal(summarizeLeaveRecordDays(rows).paid, 1.5)
})

test('only explicitly unpaid violations count and display as unpaid', () => {
  const reason = 'Qua tour CUỐI TUẦN KHÔNG phép'
  const rows = [reason, 'Quên chấm công'].map((leave_reason) => ({ leave_reason, leave_type: 'Vi phạm', calculated_days: 0 }))
  assert.equal(summarizeLeaveRecordDays(rows).unpaid, 1)
  assert.equal(displayLeaveType('Vi phạm', reason), 'Không phép (Vi phạm)')
  assert.equal(displayLeaveType('Vi phạm', 'Quên chấm công'), 'Vi phạm')
})
