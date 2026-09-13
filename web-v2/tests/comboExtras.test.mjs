import test from 'node:test'
import assert from 'node:assert/strict'
import { comboExtraSubtotal, comboUsagePreview } from '../src/lib/serviceCatalog.js'
import { comboBookingError } from '../src/lib/liveTourComboBooking.js'

test('combo covers its component while two retail services are charged separately', () => {
  const services = [{ id: 'combo', name: 'Body', price: 300000 }, { id: 'extra', name: 'Xông hơi', price: 100000 }]
  const purchase = { remaining: 1, component_balances: [{ service_id: 'combo', remaining: 1 }] }
  const items = [{ service_id: 'combo', quantity: 1 }, { service_id: 'extra', quantity: 2 }]
  assert.equal(comboBookingError(purchase, items, services), '')
  assert.deepEqual(comboUsagePreview(purchase, [{ service_items: items }], services), { units: 1, eligible: true })
  assert.equal(comboExtraSubtotal(purchase, [{ service_items: items }], services), 200000)
  assert.equal(comboExtraSubtotal(purchase, [{ service: 'Body & Xông hơi & Xông hơi' }], services), 200000)
  assert.equal(comboUsagePreview(purchase, [{ service_items: [items[1]] }], services).eligible, false)
  assert.notEqual(comboBookingError(purchase, [{ service_id: 'combo', quantity: 2 }, items[1]], services), '')
})
