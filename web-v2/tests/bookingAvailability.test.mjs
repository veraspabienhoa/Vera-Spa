import test from 'node:test'
import assert from 'node:assert/strict'
import { bookingEmployees } from '../src/lib/liveTourBooking.js'

const now = Date.parse('2026-09-13T07:00:00Z')
const base = { work_status: 'Đi làm', shift: 'Ca 1', duration: 60, started_at: new Date(now - 30 * 60000).toISOString() }
const busy = (id, remaining, extra = {}) => ({ ...base, id, status: 'Đang thực hiện', started_at: new Date(now - (60 - remaining) * 60000).toISOString(), ...extra })

test('booking shows busy staff strictly below the configured countdown, including overdue staff', () => {
  const rows = [busy('under', 29 + 59/60), busy('boundary', 30), busy('long', 31), busy('done', -1)]
  assert.deepEqual(bookingEmployees(rows, now).map(row => row.id), ['done', 'under'])
  assert.equal(bookingEmployees(rows, now + 1000).some(row => row.id === 'boundary'), true)
  assert.equal(bookingEmployees(rows, now, 15).length, 1)
  assert.equal(bookingEmployees(rows, now, 45).length, 4)
})

test('booking still hides waiting, unchecked/leave, breaks, hidden and unknown-duration employees', () => {
  const rows = [
    { ...base, id: 'idle', status: '' }, busy('waiting', 1, { status: 'Đang chờ' }),
    busy('unknown', 1, { duration: null }), busy('invalid', 1, { started_at: 'invalid' }),
    busy('leave', 1, { work_status: 'Nghỉ phép' }), busy('unchecked', 1, { shift: '' }),
    busy('hidden', 1, { hidden: true }), busy('break', 1, { break_started_at: base.started_at }),
    busy('retired', 1, { roster_eligible: false }), busy('pending', 1, { status: 'Chờ thanh toán' }),
  ]
  assert.deepEqual(bookingEmployees(rows, now, 180).map(row => row.id), ['idle'])
  for (const invalid of [null, '', '45', 0, -1, 181, true, 1.5]) {
    assert.equal(bookingEmployees([busy('busy', 40)], now, invalid).length, 0)
  }
})

test('idle suggestions use full-board STT, not imported numbers, start history or alphabetical order', () => {
  const idle = (id, extra = {}) => ({ ...base, id, name: id, service: '', status: '', ...extra })
  const rows = [
    idle('Bích Nhu', { stt: '1', sort_index: 0 }),
    idle('Cẩm Nhung', { sort_index: 1, last_assignment_display: { 'TG bắt đầu thực hiện': '13/09/2026 09:00' } }),
    idle('Tường San', { stt: '39', sort_index: 8, last_assignment_display: { 'TG bắt đầu thực hiện': '13/09/2026 10:00' } }),
    idle('Mụi Mụi', { sort_index: 5 }),
    idle('Nghỉ phép', { work_status: 'Nghỉ phép' }),
    idle('Nghỉ giữa ca', { break_started_at: base.started_at }),
    busy('busy', 20, { service: '90 VIP', request: 'YC', sort_index: -1 }),
  ]
  const records = rows.map((row, index) => ({ _employee_id: row.id, STT: [18, 12, 1, 6, 2, 3, 25][index] }))
  const originalIds = rows.map(row => row.id)
  const expected = ['Tường San', 'Mụi Mụi', 'Cẩm Nhung', 'Bích Nhu', 'busy']
  assert.deepEqual(bookingEmployees(rows, now, 30, records).map(row => row.id), expected)
  assert.deepEqual(rows.map(row => row.id), originalIds)
  assert.deepEqual(bookingEmployees(rows.map(row => ({ ...row, manual_order: true })), now, 30, records).map(row => row.id), expected)
  // A newer board snapshot controls the next render, even with unchanged state order.
  const moved = records.map(row => ({ ...row, STT: row._employee_id === 'Bích Nhu' ? 1 : Number(row.STT) + 1 }))
  assert.equal(bookingEmployees(rows, now, 30, moved)[0].id, 'Bích Nhu')
})

test('missing/invalid board STT uses stable state order after numbered idle employees', () => {
  const rows = [3, 1, 2].map(id => ({ ...base, id, service: '', status: '', sort_index: id }))
  const records = [{ employee_id: 3, STT: '10' }, { employee_id: 2, STT: '' }, { employee_id: 1, STT: -1 }]
  assert.deepEqual(bookingEmployees(rows, now, 30, records).map(row => row.id), [3, 1, 2])
  assert.deepEqual(bookingEmployees(rows, now).map(row => row.id), [1, 2, 3])
})
