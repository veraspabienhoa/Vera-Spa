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
