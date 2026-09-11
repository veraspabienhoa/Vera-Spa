import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { paymentQrUrl, receiptNumber, tipAmount, tipMoney } from '../src/lib/paymentPresentation.js'
const bank = { enabled: true, bank_id: '970436', account_no: '00123456789', account_name: 'VERA SPA' }
test('QR encodes exact bank, leading-zero account and amount; invalid or zero amounts have no QR', () => {
  const url = new URL(paymentQrUrl(bank, 150000, 'LIVE-20260911-0005'))
  assert.ok(url.pathname.includes('00123456789'))
  assert.equal(url.searchParams.get('amount'), '150000')
  assert.equal(url.searchParams.get('addInfo'), 'VERA-20260911-0005')
  for (const amount of [0, -1, NaN, 1.5]) assert.equal(paymentQrUrl(bank, amount), '')
  assert.equal(paymentQrUrl({ ...bank, enabled: false }, 1000), '')
  assert.equal(tipAmount('10.000 đ'), 10000)
  assert.equal(tipMoney(10000), '10.000 đ')
  assert.equal(receiptNumber('CUSTOM-1'), 'CUSTOM-1')
})
const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true, url: 'https://example.test' })
Object.defineProperties(globalThis, { window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true }, navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true } })
const { createRoot } = await import('react-dom/client')
const built = await build({ stdin: { contents: "export {default as Settings} from './src/components/LiveTourPaymentSettings'; export {default as Tip} from './src/components/LiveTourTipInput'; export {default as Receipt} from './src/components/LiveTourReceipt';", resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' } })
const module = { exports: {} }
new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
const { Settings, Tip, Receipt } = module.exports
const cards = [50000, 100000, 200000, 300000, 500000, 10000].map(amount => ({ id: String(amount), name: tipMoney(amount), amount }))
const type = async (input, value) => act(() => { Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value); input.dispatchEvent(new dom.window.Event('input', { bubbles: true })) })
test('new TIP input fills numeric value, formats on blur, sorts and saves opening preference', async () => {
 const root = createRoot(document.querySelector('#root')); let saved
 try {
  await act(() => root.render(React.createElement(Settings, { value: { tip_cards: cards, auto_print: true }, onSave: value => { saved = value } })))
  assert.equal(document.querySelector('[aria-label="Mệnh giá thẻ TIP 1"]').value, '10000')
  await act(() => [...document.querySelectorAll('button')].find(x => x.textContent.includes('Thêm thẻ TIP')).click())
  const input = document.querySelector('[aria-label="Tên thẻ TIP 7"]')
  await act(() => input.focus()); await type(input, '25000')
  assert.equal(document.querySelector('[aria-label="Mệnh giá thẻ TIP 7"]').value, '25000')
  await act(() => input.blur())
  assert.equal(document.querySelector('[aria-label="Tên thẻ TIP 2"]').value, '25.000 đ')
  await act(() => document.querySelector('input[type=checkbox]').click())
  await act(() => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
  assert.equal(saved.open_receipt, false); assert.equal(saved.auto_print, false)
  assert.deepEqual(saved.tip_cards.map(x => x.amount), [10000, 25000, 50000, 100000, 200000, 300000, 500000])
 } finally { await act(() => root.unmount()) }
})
test('all TIP cards are visible and receipt shows VERA brand, address and exact QR amount', async () => {
 const root = createRoot(document.querySelector('#root'))
 try {
  await act(() => root.render(React.createElement(Tip, { form: { tip_mode: 'cards', tip_card_ids: [] }, setForm() {}, cards, total: 0, preferenceKey: 'test' })))
  assert.equal(document.querySelectorAll('.tour-tip-cards button').length, 6)
  assert.equal(document.querySelector('.tour-tip-cards button').textContent, '10.000 đ')
  await act(() => root.render(React.createElement(Receipt, { invoice: { id: 'i', bill_no: 'LIVE-20260911-0005', total: 150000, entries: [] }, paymentSettings: { bank }, onClose() {} })))
  assert.equal(document.querySelector('.tour-receipt h2').textContent, 'VERA SPA')
  assert.equal(document.querySelector('.vera-receipt-address').textContent, '193 Trương Định, Tam Hiệp, Đồng Nai')
  assert.ok(document.querySelector('.tour-receipt').textContent.includes('VERA-20260911-0005'))
  assert.equal(new URL(document.querySelector('.tour-payment-qr img').src).searchParams.get('amount'), '150000')
 } finally { await act(() => root.unmount()) }
})
test.after(() => dom.window.close())
