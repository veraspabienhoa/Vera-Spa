import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const require = createRequire(import.meta.url)
const built = await build({ entryPoints: ['src/pages/LiveTourPage.jsx'], bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime', 'lucide-react'], loader: { '.css': 'empty' }, plugins: [{ name: 'api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__quickApi;', loader: 'js' }))
} }] })
test('automatic combo preview, required date, customer switch and live refresh', async () => {
  const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'http://localhost', pretendToBeVisual: true })
  const keys = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', '__quickApi']
  const previous = Object.fromEntries(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const services = [{ id: 'body', name: 'Body 90', price: 200000, ticket_units: 1, active: true }]
  const customers = [{ id: 'c1', name: 'Khách Combo', phone: '0901234567', combo_purchases: [{ id: 'p1', combo_name: 'Combo Body', remaining: 3, component_balances: [{ service_id: 'body', total: 3, remaining: 3 }] }] }, { id: 'c2', name: 'Khách thường', combo_purchases: [] }]
  const data = { revision: 1, columns: ['Tên nhân viên', 'Vào ca'], records: [{ _id: 'e1', 'Tên nhân viên': 'An', 'Vào ca': 'Ca 1' }], state: { employees: [{ id: 'e1', name: 'An', work_status: 'Đi làm', shift: 'Ca 1' }], services, customers }, customers, services, catalogs: { rooms: [{ id: 'r1', name: '1.1' }] }, capabilities: { payment: true, booking: true, customers: true }, payment_settings: {} }
  let reads = 0
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true, __quickApi: { liveTour: async () => { reads++; return data } } })) Object.defineProperty(globalThis, key, { value, configurable: true })
  const { createRoot } = await import('react-dom/client')
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(document.querySelector('#root'))
  const click = async node => { assert.ok(node); await act(async () => node.dispatchEvent(new window.MouseEvent('click', { bubbles: true }))) }
  const input = text => { const label = [...document.querySelectorAll('.live-tour-modal label')].find(item => item.textContent.trim() === text); return label?.querySelector('input') || document.getElementById(label?.htmlFor) }
  const choose = async (label, text) => { await act(async () => input(label).dispatchEvent(new window.FocusEvent('focusin', { bubbles: true }))); await click([...document.querySelectorAll('[role="option"]')].find(node => node.textContent.includes(text))) }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
    await click([...document.querySelectorAll('button')].find(node => node.textContent.trim() === 'Thanh toán nhanh'))
    const labels = [...document.querySelectorAll('.live-tour-modal label')].map(node => node.textContent.trim())
    assert.ok(labels.indexOf('Nhân viên') < labels.indexOf('Dịch vụ'))
    assert.equal(input('Ngày booking').value, '')
    assert.equal(input('Ngày booking').required, true)
    await choose('Khách hàng', 'Khách Combo')
    assert.equal(input('Dịch vụ (tự động từ combo)').required, false)
    assert.match(document.querySelector('.live-tour-checkout-preview').textContent, /Body 90/)
    assert.match(document.querySelector('.live-tour-combo-deduction').textContent, /1 lượt/)
    const before = reads
    await act(async () => window.dispatchEvent(new window.Event('vera:leave-updated')))
    assert.ok(reads > before)
    assert.equal(input('Ngày booking').value, '')
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input('Khách hàng'), '')
      input('Khách hàng').dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    await choose('Khách hàng', 'Khách thường')
    assert.equal(input('Dịch vụ').required, true)
    assert.equal(document.querySelector('.live-tour-combo-deduction'), null)
  } finally {
    await act(() => root.unmount()); dom.window.close()
    for (const [key, value] of Object.entries(previous)) { if (value) Object.defineProperty(globalThis, key, value); else delete globalThis[key] }
  }
})
