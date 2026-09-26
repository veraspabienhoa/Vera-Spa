import assert from 'node:assert/strict'
import test from 'node:test'
import { filterTourRows } from '../src/lib/liveTourFilters.js'

import {
  defaultRevenueTipStart,
  revenueTipRowDate,
  revenueTipTotal,
  revenueTipValue,
} from '../src/lib/revenueTipPeriod.js'

test('revenue TIP period starts on day 1 for the first half and day 16 for the second half', () => {
  assert.equal(defaultRevenueTipStart('2026-09-01'), '2026-09-01')
  assert.equal(defaultRevenueTipStart('2026-09-15'), '2026-09-01')
  assert.equal(defaultRevenueTipStart('2026-09-16'), '2026-09-16')
  assert.equal(defaultRevenueTipStart('2026-09-30'), '2026-09-16')
})

test('revenue TIP uses Vietnam business dates and sums only the selected period', () => {
  const rows = [
    { business_date: '2026-09-01', tip: 100000 },
    { effective_at: '2026-09-13T20:00:00+07:00', tip: 50000 },
    { business_date: '2026-09-16', tip: 30000 },
    { business_date: '2026-08-31', tip: 900000 },
  ]
  assert.equal(revenueTipRowDate(rows[1]), '2026-09-13')
  assert.equal(revenueTipTotal(rows, '2026-09-01', '2026-09-13'), 150000)
  assert.equal(revenueTipTotal(rows, '2026-09-16', '2026-09-30'), 30000)
})


test('revenue TIP accepts formatted money and uses the same calendar date as Reports', () => {
  assert.equal(revenueTipValue('100.000đ'), 100000)
  assert.equal(revenueTipValue('50,000'), 50000)
  assert.equal(revenueTipRowDate({
    business_date: '2026-09-13',
    effective_at: '2026-09-14T00:30:00+07:00',
  }), '2026-09-14')
  assert.equal(revenueTipTotal([
    { business_date: '13/09/2026', tip: '100.000đ' },
    { business_date: '2026-09-13', tip: '50,000' },
    { business_date: '2026-09-14', tip: 900000 },
  ], '2026-09-01', '2026-09-13'), 150000)
})

test('Revenue and Reports agree across the period boundary and backdated timestamps', () => {
  const rows = [
    { business_date: '2026-09-16', effective_at: '2026-09-16T12:00:00+07:00', tip: 100000000 },
    { business_date: '2026-09-24', effective_at: '2026-09-24T23:59:59+07:00', tip: 130310000 },
    { business_date: '2026-09-24', effective_at: '2026-09-24T17:00:00Z', tip: 85410000 },
  ]
  const expected = filterTourRows(rows, { date_from: '2026-09-16', date_to: '2026-09-24' }).reduce((sum, row) => sum + row.tip, 0)
  assert.equal(expected, 230310000)
  assert.equal(revenueTipTotal(rows, '2026-09-16', '2026-09-24'), expected)
  assert.equal(revenueTipTotal(rows, '2026-09-25', '2026-09-25'), 85410000)
  const backdated = { business_date: '2026-09-25', effective_at: '2026-09-24T23:59:59', created_at: '2026-09-26T00:00:00Z', tip: 123 }
  assert.equal(revenueTipRowDate(backdated), '2026-09-24')
  assert.equal(revenueTipRowDate({ business_date: '2026-09-25', booked_at: '2026-09-24T16:59:59Z' }), '2026-09-24')
  assert.equal(revenueTipTotal([backdated], '2026-09-24', '2026-09-24'), 123)
})
