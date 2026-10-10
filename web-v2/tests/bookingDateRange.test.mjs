import test from 'node:test'
import assert from 'node:assert/strict'
import { bookingDateRange } from '../src/lib/bookingDateRange.js'
test('Vietnam midnight and Monday weeks cross month/year correctly',()=>{
 const now=new Date('2026-12-31T18:00:00Z')
 assert.deepEqual(bookingDateRange('today',now),{date_from:'2027-01-01',date_to:'2027-01-01'})
 assert.deepEqual(bookingDateRange('yesterday',now),{date_from:'2026-12-31',date_to:'2026-12-31'})
 assert.deepEqual(bookingDateRange('tomorrow',now),{date_from:'2027-01-02',date_to:'2027-01-02'})
 assert.deepEqual(bookingDateRange('week',now),{date_from:'2026-12-28',date_to:'2027-01-03'})
 assert.deepEqual(bookingDateRange('next-week',now),{date_from:'2027-01-04',date_to:'2027-01-10'})
})
test('yesterday follows Vietnam midnight, leap days and month boundaries',()=>{
 for (const [now, expected] of [
  ['2026-10-10T16:59:59Z','2026-10-09'],
  ['2026-10-10T17:00:00Z','2026-10-10'],
  ['2024-03-01T01:00:00Z','2024-02-29'],
  ['2026-03-01T01:00:00Z','2026-02-28'],
 ]) assert.deepEqual(bookingDateRange('yesterday',new Date(now)),{date_from:expected,date_to:expected})
})
