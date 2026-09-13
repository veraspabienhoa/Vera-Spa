import test from 'node:test'
import assert from 'node:assert/strict'
import { invoiceMoneyValues, invoiceServiceSubtotal } from '../src/lib/liveTourInvoiceMoney.js'

test('invoice money separates service discount tip and total', () => {
  assert.deepEqual(invoiceMoneyValues({ subtotal: 500000, discount: 50000, tip: 100000, total: 550000 }), {
    service: 500000, discount: 50000, tip: 100000, total: 550000,
  })
})

test('combo redemption only reports extra services as service money', () => {
  assert.equal(invoiceServiceSubtotal({ payment_method: 'COMBO', subtotal: 400000, combo_extra_subtotal: 150000 }), 150000)
  assert.equal(invoiceServiceSubtotal({ payment_method: 'COMBO', purchased_combo_id: 'sale-1', subtotal: 400000 }), 400000)
})

test('legacy invoices derive service money from entries', () => {
  assert.equal(invoiceServiceSubtotal({ entries: [{ price: 90000 }, { price: '210000' }] }), 300000)
})
