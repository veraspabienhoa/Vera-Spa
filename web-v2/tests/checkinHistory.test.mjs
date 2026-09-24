import test from 'node:test'
import assert from 'node:assert/strict'
import { CHECKIN_PRESETS, checkinDateRange, checkinQuery, checkinRangeError, initialCheckinFilters } from '../src/lib/checkinHistory.js'

test('quick periods use Vietnam dates across month, year and week boundaries', () => {
  const now = new Date('2026-12-31T18:00:00Z')
  assert.deepEqual(checkinDateRange('today', now), { date_from: '2027-01-01', date_to: '2027-01-01' })
  assert.deepEqual(checkinDateRange('last-month', now), { date_from: '2026-12-01', date_to: '2026-12-31' })
  assert.deepEqual(checkinDateRange('week', now), { date_from: '2026-12-28', date_to: '2027-01-03' })
  assert.deepEqual(checkinDateRange('last-week', now), { date_from: '2026-12-21', date_to: '2026-12-27' })
  assert.deepEqual(checkinDateRange('month', new Date('2024-02-10T12:00:00Z')), { date_from: '2024-02-01', date_to: '2024-02-29' })
})
test('all option is explicitly bounded to 63 inclusive days', () => {
  assert.equal(CHECKIN_PRESETS.find(([id]) => id === 'all')[1], 'Tất cả')
  assert.equal(initialCheckinFilters(new Date('2026-09-24T10:00:00Z')).preset, 'today')
  const range = checkinDateRange('all', new Date('2026-09-24T10:00:00Z'))
  assert.equal((Date.parse(range.date_to) - Date.parse(range.date_from)) / 86400000, 62)
  assert.equal(checkinRangeError(range), '')
  assert.match(checkinRangeError({ date_from: '2026-01-01', date_to: '2026-09-30' }), /63/)
  assert.match(checkinRangeError({ ...range, event_date: '2026-01-01' }), /khoảng/)
})
test('query includes exact applied detailed filters and does not send preset to API', () => {
  const filters = { ...initialCheckinFilters(new Date('2026-09-24T10:00:00Z')), employee: ' Ánh ', event_id: '12', status: '0', event_type: 'A', event_date: '2026-09-23' }
  assert.deepEqual(checkinQuery(filters), { source: 'facegate_saved', start: '2026-09-24', end: '2026-09-24', employee: 'Ánh', event_id: '12', status: '0', event_type: 'A', event_date: '2026-09-23' })
})
