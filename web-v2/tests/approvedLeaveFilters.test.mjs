import test from 'node:test'
import assert from 'node:assert/strict'
import { approvedLeaveStatus, filterApprovedLeaveItems, vietnamToday } from '../src/lib/approvedLeaveFilters.js'

const TODAY = '2026-10-02'
const leaves = [
  { id: 'a1', employee_name: 'Nguyễn An Nhiên', request_type: 'Nghỉ Phép năm', start_date: '2026-10-02', end_date: '2026-10-03' },
  { id: 'l1', employee_name: 'Linh Đan', request_type: 'Nghỉ làm đẹp', start_date: '2026-10-08', end_date: '2026-10-08' },
  { id: 'a2', employee_name: 'Phương Vy', request_type: 'Nghỉ Phép năm', start_date: '2026-09-29', end_date: '2026-10-01' },
  { id: 'a3', employee_name: 'Hải My', request_type: 'Nghỉ Phép năm', start_date: '2026-10-10', end_date: '2026-10-10', leave_completed: true },
]
const resignations = [{ id: 'r1', employee_name: 'Minh Anh', request_type: 'Nghỉ việc', start_date: '2026-11-01' }]

test('Vietnam date and leave status categories use inclusive stay dates', () => {
  assert.equal(vietnamToday(new Date('2026-10-01T18:00:00Z')), TODAY)
  assert.deepEqual(approvedLeaveStatus(leaves[0], TODAY), { id: 'active', label: 'Đang nghỉ' })
  assert.deepEqual(approvedLeaveStatus(leaves[1], TODAY), { id: 'waiting', label: 'Chờ nghỉ' })
  assert.deepEqual(approvedLeaveStatus(leaves[2], TODAY), { id: 'completed', label: 'Đã kết thúc kỳ nghỉ' })
  assert.deepEqual(approvedLeaveStatus(leaves[3], TODAY), { id: 'completed', label: 'Đã kết thúc kỳ nghỉ' })
  assert.deepEqual(approvedLeaveStatus(resignations[0], TODAY), { id: 'resignation', label: 'Nghỉ việc' })
})

test('approved request filters include each request type and current leave status', () => {
  const ids = (filter) => filterApprovedLeaveItems(leaves, resignations, { filter, today: TODAY }).map((item) => item.id)
  assert.deepEqual(ids('all'), ['a1', 'l1', 'a2', 'a3', 'r1'])
  assert.deepEqual(ids('annual'), ['a1', 'a2', 'a3'])
  assert.deepEqual(ids('long'), ['l1'])
  assert.deepEqual(ids('active'), ['a1'])
  assert.deepEqual(ids('waiting'), ['l1'])
  assert.deepEqual(ids('completed'), ['a2', 'a3'])
  assert.deepEqual(ids('resignation'), ['r1'])
})

test('employee search ignores Vietnamese diacritics and combines with a status filter', () => {
  const results = filterApprovedLeaveItems(leaves, resignations, {
    filter: 'annual', search: 'nguyen an nhien', today: TODAY,
  })
  assert.deepEqual(results.map((item) => item.id), ['a1'])
})
