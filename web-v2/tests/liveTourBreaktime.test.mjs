import test from 'node:test'
import assert from 'node:assert/strict'
import { breakCellValue } from '../src/lib/liveTourBreaktime.js'
import { bookingEmployees } from '../src/lib/liveTourBooking.js'

test('attendance break counts down in place, shows overtime and stops on return', () => {
  const record = { _attendance_break_active: true, _break_from_attendance: true,
    _break_countdown_deadline: '2026-09-12T16:15:00+07:00', 'TG nghỉ còn lại': 15,
    'Giờ ra': '2026-09-12T15:30:00+07:00', 'Giờ vào': '' }
  assert.equal(breakCellValue(record, 'TG nghỉ còn lại', Date.parse('2026-09-12T16:05:00+07:00')), 10)
  assert.equal(breakCellValue(record, 'TG nghỉ còn lại', Date.parse('2026-09-12T16:17:00+07:00')), -2)
  assert.equal(breakCellValue(record, 'Giờ ra', 0), '15:30:00')
  assert.equal(breakCellValue(record, 'Giờ vào', 0), '')
  record._attendance_break_active = false
  record['TG nghỉ còn lại'] = 0
  assert.equal(breakCellValue(record, 'TG nghỉ còn lại', Date.now()), 0)
  assert.equal(breakCellValue({ 'TG nghỉ còn lại': 30 }, 'TG nghỉ còn lại', 0), 30)
})

test('booking selector excludes an open break even after deadline and allows confirmed return', () => {
  const worker = { id: 'e1', name: 'An', work_status: 'Đi làm', shift: 'Ca 1',
    break_started_at: '2026-09-12T15:30:00+07:00' }
  assert.deepEqual(bookingEmployees([worker]), [])
  worker.clock_in = '2026-09-12T17:00:00+07:00'
  worker.break_started_at = ''
  assert.equal(bookingEmployees([worker])[0].id, 'e1')
})
