import test from 'node:test'
import assert from 'node:assert/strict'
import { checkoutBookingTime } from '../src/lib/liveTourBooking.js'
import { comboUsagePreview, vietnamDate } from '../src/lib/serviceCatalog.js'

test('an old pending bill can use a combo valid at booking although expired today', () => {
  const now = Date.parse('2026-09-10T15:00:00+07:00')
  const entries = [{ service: 'Body', booked_at: '2026-08-02T23:30:00+07:00' }]
  const pending = { effective_at: entries[0].booked_at, created_at: '2026-08-03T01:00:00+07:00' }
  const purchase = { remaining: 2, active: true, starts_on: '2026-08-01', unlimited: false, expires_on: '2026-08-05' }
  const bookingDay = vietnamDate(checkoutBookingTime(entries, pending, now))
  assert.equal(bookingDay, '2026-08-02')
  assert.equal(comboUsagePreview(purchase, entries, [], bookingDay).eligible, true)
  assert.equal(comboUsagePreview(purchase, entries, [], vietnamDate(now)).eligible, false)
  assert.equal(comboUsagePreview({ ...purchase, remaining: 0 }, entries, [], bookingDay).eligible, false)
})

test('checkout date follows corrected pending date then earliest source booking and legacy creation', () => {
  const now = Date.parse('2026-09-10T15:00:00+07:00')
  const entries = [{ booked_at: 'bad' }, { booked_at: '2026-09-02T19:00:00+07:00' }, { booked_at: '2026-09-01T19:00:00+07:00' }]
  assert.equal(vietnamDate(checkoutBookingTime(entries, { effective_at: '2026-08-31T23:00:00+07:00' }, now)), '2026-08-31')
  assert.equal(vietnamDate(checkoutBookingTime(entries, { effective_at: 'bad' }, now)), '2026-09-01')
  assert.equal(vietnamDate(checkoutBookingTime([], { created_at: '2026-08-30T23:00:00+07:00' }, now)), '2026-08-30')
  assert.equal(checkoutBookingTime([], {}, now), now)
})
