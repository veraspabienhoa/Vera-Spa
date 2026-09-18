import assert from 'node:assert/strict'
import test from 'node:test'

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


test('revenue TIP accepts formatted money and prioritizes the report business date', () => {
  assert.equal(revenueTipValue('100.000đ'), 100000)
  assert.equal(revenueTipValue('50,000'), 50000)
  assert.equal(revenueTipRowDate({
    business_date: '2026-09-13',
    effective_at: '2026-09-14T00:30:00+07:00',
  }), '2026-09-13')
  assert.equal(revenueTipTotal([
    { business_date: '13/09/2026', tip: '100.000đ' },
    { business_date: '2026-09-13', tip: '50,000' },
    { business_date: '2026-09-14', tip: 900000 },
  ], '2026-09-01', '2026-09-13'), 150000)
})
