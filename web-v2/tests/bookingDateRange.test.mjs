import test from 'node:test'
import assert from 'node:assert/strict'
import { bookingDateRange } from '../src/lib/bookingDateRange.js'
test('Vietnam midnight and Monday weeks cross month/year correctly',()=>{
 const now=new Date('2026-12-31T18:00:00Z')
 assert.deepEqual(bookingDateRange('today',now),{date_from:'2027-01-01',date_to:'2027-01-01'})
 assert.deepEqual(bookingDateRange('tomorrow',now),{date_from:'2027-01-02',date_to:'2027-01-02'})
 assert.deepEqual(bookingDateRange('week',now),{date_from:'2026-12-28',date_to:'2027-01-03'})
 assert.deepEqual(bookingDateRange('next-week',now),{date_from:'2027-01-04',date_to:'2027-01-10'})
})
