import test from 'node:test'
import assert from 'node:assert/strict'

import {
  LETAN_REASON_GROUPS,
  canDeleteLeaveRecord,
  canEditLeaveRecord,
  letanReasonChoices,
} from '../src/lib/leaveRecordPermissions.js'

const today = '2026-09-04'
const row = (role, date, reason, allowed = true) => ({
  role,
  allowedByPermission: allowed,
  recordDate: date,
  currentReason: reason,
  today,
})

test('Admin can always edit and delete, including past records', () => {
  const past = row('admin', '2026-09-03', 'Nghỉ CÓ phép', false)
  assert.equal(canEditLeaveRecord(past), true)
  assert.equal(canDeleteLeaveRecord(past), true)
})

test('Lễ tân cannot edit or delete past records', () => {
  const past = row('letan', '2026-09-03', 'Nghỉ CÓ phép')
  assert.equal(canEditLeaveRecord(past), false)
  assert.equal(canDeleteLeaveRecord(past), false)
})

test('Lễ tân can only edit within the same three-choice group today', () => {
  const current = row('letan', today, 'Nghỉ CÓ phép', false)
  assert.equal(canEditLeaveRecord(current), true)
  assert.equal(canDeleteLeaveRecord(current), false)
  assert.deepEqual(letanReasonChoices('letan', today, current.currentReason, today), LETAN_REASON_GROUPS[0])
})

test('Lễ tân today non-group and future records follow permissions', () => {
  for (const date of [today, '2026-09-05']) {
    assert.equal(canEditLeaveRecord(row('letan', date, 'Nghỉ lý do khác', true)), true)
    assert.equal(canDeleteLeaveRecord(row('letan', date, 'Nghỉ lý do khác', true)), true)
    assert.equal(canEditLeaveRecord(row('letan', date, 'Nghỉ lý do khác', false)), false)
    assert.equal(canDeleteLeaveRecord(row('letan', date, 'Nghỉ lý do khác', false)), false)
  }
})

test('Quản lý follows the configured permissions without frontend type locking', () => {
  assert.equal(canEditLeaveRecord(row('quanly', today, 'Nghỉ CÓ phép', true)), true)
  assert.equal(canDeleteLeaveRecord(row('quanly', today, 'Nghỉ CÓ phép', true)), true)
  assert.equal(canEditLeaveRecord(row('quanly', today, 'Nghỉ CÓ phép', false)), false)
  assert.equal(canDeleteLeaveRecord(row('quanly', today, 'Nghỉ CÓ phép', false)), false)
})
