import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const built = await build({ entryPoints: [fileURLToPath(new URL('../src/components/LiveTourReceipt.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' } })
const module = { exports: {} }
new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
const Receipt = module.exports.default
const bank = { enabled: true, bank_id: 'VCB', account_no: '0123456789', account_name: 'User 2' }

test('receipt shows separate booking users, VN dates and payment user; reprinting retains cashier QR', async () => {
  const root = createRoot(document.getElementById('root'))
  const invoice = { id: 'bill', bill_no: 'VERA-1', actor: 'user2',
    effective_at: '2026-09-11T10:00:00+07:00', recorded_at: '2026-09-12T11:30:00+07:00',
    payment_bank: bank, total: 300, subtotal: 300, payment_method: 'CHUYỂN KHOẢN',
    entries: [{ booked_at: '2026-09-11T10:00:00+07:00', booking_actor: 'user1', service: 'Body', price: 100 },
      { booked_at: '2026-09-11T12:00:00+07:00', booking_actor: 'user3', service: 'Foot', price: 200 }] }
  const render = async (current, viewerBank) => act(async () => root.render(React.createElement(Receipt, {
    invoice: current, onClose() {}, paymentSettings: { bank: viewerBank, user_bank: viewerBank },
  })))
  try {
    await render(invoice, { ...bank, account_no: '999999999' })
    const receipt = document.getElementById('live-tour-receipt')
    assert.match(receipt.textContent, /Ngày giờ booking · Người đặt:.*10:00:00.*11\/9\/2026.*user1/)
    assert.match(receipt.textContent, /Ngày giờ booking · Người đặt:.*12:00:00.*11\/9\/2026.*user3/)
    assert.match(receipt.textContent, /Ngày giờ thanh toán · Người thanh toán:.*11:30:00.*12\/9\/2026.*user2/)
    assert.match(receipt.querySelector('img').src, /VCB-0123456789-compact2/)
    await render(invoice, { ...bank, account_no: '888888888' })
    assert.match(receipt.querySelector('img').src, /VCB-0123456789-compact2/)
    await render({ ...invoice, payment_bank: undefined, entries: [{ service: 'Body', price: 300 }] }, bank)
    assert.equal(receipt.querySelector('img'), null)
    assert.match(receipt.textContent, /Chưa ghi nhận người đặt/)
    await render({ ...invoice, payment_method: 'COMBO', subtotal: 300, combo_covered_amount: 300, total: 50, tip: 50 }, bank)
    assert.match(receipt.textContent, /Tiền dịch vụ0 đ/)
    assert.deepEqual([...receipt.querySelectorAll('tbody tr')].map(row => row.lastElementChild.textContent), ['0 đ', '0 đ'])
    assert.match(receipt.textContent, /Tổng tiền50 đ/)
    await render({ ...invoice, purchased_combo_id: 'sale', entries: [{ service: 'Mua Combo', price: 300 }] }, bank)
    assert.match(receipt.textContent, /Tiền dịch vụ300 đ/)
  } finally {
    await act(async () => root.unmount())
  }
})
