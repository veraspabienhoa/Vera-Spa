import test from 'node:test'
import assert from 'node:assert/strict'
import { bookingEmployees } from '../src/lib/liveTourBooking.js'

test('booking hides waiting and over 30 minutes; reappears at the exact boundary', () => {
  const now = Date.parse('2026-09-13T07:00:00Z')
  const base = { work_status: 'Đi làm', shift: 'Ca 1', duration: 60, started_at: new Date(now - 30 * 60000).toISOString() }
  const rows = [
    { ...base, id: 'idle', status: '' },
    { ...base, id: 'waiting', status: 'Đang chờ' },
    { ...base, id: 'boundary', status: 'Đang thực hiện' },
    { ...base, id: 'long', status: 'Đang thực hiện', started_at: new Date(now - 30 * 60000 + 1000).toISOString() },
    { ...base, id: 'unknown', status: 'Đang thực hiện', duration: null },
    { ...base, id: 'leave', work_status: 'Nghỉ phép' },
  ]
  assert.deepEqual(new Set(bookingEmployees(rows, now).map(row => row.id)), new Set(['idle', 'boundary']))
  assert.ok(bookingEmployees(rows, now + 1000).some(row => row.id === 'long'))
})
