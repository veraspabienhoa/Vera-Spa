import test from 'node:test'
import assert from 'node:assert/strict'
import { usesComboTicket } from '../src/lib/paymentPresentation.js'
test('ticket highlight covers reservations and mixed payments without marking combo sales or ordinary customers', () => {
  for (const value of [{combo_purchase_id:'p'}, {entries:[{combo_purchase_id:'p'}]}, {payment_method:'COMBO'}, {payment_method:'TIỀN MẶT',entries:[{combo_purchase_id:'p'}]}]) assert.equal(usesComboTicket(value), true)
  for (const value of [null, {}, {customer_id:'c'}, {purchased_combo_id:'sale',payment_method:'COMBO'}]) assert.equal(usesComboTicket(value), false)
})
