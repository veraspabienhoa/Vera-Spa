import test from 'node:test'
import assert from 'node:assert/strict'
import { revenueEntryDays, revenueEntryWindowValue, revenueEntryDateAllowed } from '../src/lib/revenueEntryWindow.js'

test('role and account scopes distinguish explicit all days from inheritance', () => {
  const data = { revenue_entry_windows: { roles: { letan: 3 }, accounts: { Cashier: null, other: 7 } } }
  assert.equal(revenueEntryDays(data, 'account', 'cashier', 'letan'), null)
  assert.equal(revenueEntryDays(data, 'account', 'new', 'letan'), 3)
  assert.equal(revenueEntryDays(data, 'account', 'other', 'letan'), 7)
  assert.equal(revenueEntryDays(data, 'account', 'other', 'admin'), null)
  assert.equal(revenueEntryDays(data, 'role', 'letan'), 3)
})

test('custom days reject blank fractions and invalid range', () => {
  for (const value of ['', ' ', 0, -1, '1.5', 36501]) assert.throws(() => revenueEntryWindowValue(value))
  assert.equal(revenueEntryWindowValue('11'), 11)
  assert.equal(revenueEntryWindowValue(null), null)
})

test('transaction dates enforce inclusive server bounds across month boundary', () => {
  const window = { min_date: '2026-02-27', max_date: '2026-03-01' }
  for (const value of ['2026-02-27', '2026-02-28', '2026-03-01']) assert.ok(revenueEntryDateAllowed(value, window))
  for (const value of ['', '2026-02-26', '2026-03-02']) assert.equal(revenueEntryDateAllowed(value, window), false)
  assert.ok(revenueEntryDateAllowed('2020-01-01', { min_date: '', max_date: '' }))
})
