import assert from 'node:assert/strict'
import test from 'node:test'
import { autoQuickCombo, quickComboEntry, quickComboPurchases } from '../src/lib/liveTourQuickCombo.js'

const day = '2026-09-12'
const services = [{ id: 'body', name: 'Body 90', price: 200000 }, { id: 'steam', name: 'Xông hơi', price: 100000 }]
const purchase = { id: 'p', combo_name: 'Combo Body', remaining: 5, component_balances: [
  { service_id: 'body', remaining: 3, total: 3 }, { service_id: 'steam', remaining: 2, total: 2 },
] }
const customer = { id: 'c', combo_purchases: [purchase] }

test('customer combo is selected without an individual service and defaults to one use per component', () => {
  const form = autoQuickCombo({ customer_id: 'c', service_id: 'stale', booking_date: day, discount: '200', payment_method: 'TIỀN MẶT' }, [customer], services, day)
  assert.equal(form.combo_purchase_id, 'p')
  assert.equal(form.service_id, '')
  assert.equal(form.payment_method, 'COMBO')
  assert.equal(form.discount, '0')
  const preview = quickComboEntry(quickComboPurchases(customer, services, day)[0], services, day)
  assert.deepEqual(preview.service_items.map(item => item.quantity), [1, 1])
  assert.equal(preview.price, 300000)
  assert.equal(customer.combo_purchases[0].remaining, 5)
})

test('ignore expired, deleted, future, exhausted and fully reserved combos', () => {
  const invalid = [
    { ...purchase, id: 'expired', unlimited: false, expires_on: '2026-09-11' },
    { ...purchase, id: 'deleted', deleted_at: '2026-09-01' },
    { ...purchase, id: 'future', starts_on: '2026-09-13' },
    { ...purchase, id: 'empty', remaining: 0 },
    { ...purchase, id: 'reserved', booking_remaining: 0 },
  ]
  const owner = { id: 'c', combo_purchases: [...invalid, purchase] }
  assert.deepEqual(quickComboPurchases(owner, services, day).map(item => item.id), ['p'])
  assert.equal(autoQuickCombo({ customer_id: 'c' }, [owner], services, day).combo_purchase_id, 'p')
})

test('booking date, not wall clock, determines which combos and components can be used', () => {
  const owner = { id: 'c', combo_purchases: [{ ...purchase, unlimited: false, expires_on: '2026-09-10' }] }
  assert.equal(autoQuickCombo({ customer_id: 'c', booking_date: '2026-09-09' }, [owner], services, day).combo_purchase_id, 'p')
  assert.equal(autoQuickCombo({ customer_id: 'c', booking_date: day }, [owner], services, day).combo_purchase_id, '')
})

test('component reservations are preserved and generic tickets never invent a service', () => {
  const reserved = { ...purchase, component_balances: purchase.component_balances.map((part, i) => ({ ...part, booking_remaining: i ? 2 : 0 })) }
  const available = quickComboPurchases({ combo_purchases: [reserved] }, services, day)[0]
  assert.deepEqual(quickComboEntry(available, services, day).service_items.map(item => item.service_id), ['steam'])
  const generic = quickComboEntry({ id: 'legacy', combo_name: 'Combo 13', remaining: 3 }, services, day)
  assert.equal(generic.service, 'Sử dụng combo: Combo 13')
  assert.equal(generic.price, 0)
  assert.equal(generic.price_source, 'combo_ticket')
  assert.deepEqual(generic.service_items, [])
})

test('changing customer cannot retain a previous customer combo', () => {
  const form = autoQuickCombo({ customer_id: 'other', combo_purchase_id: 'p', payment_method: 'COMBO' }, [customer, { id: 'other', combo_purchases: [] }], services, day)
  assert.equal(form.combo_purchase_id, '')
  assert.equal(form.payment_method, 'TIỀN MẶT')
})
