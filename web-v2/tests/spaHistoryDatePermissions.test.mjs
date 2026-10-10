import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/SpaManagementPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'fixture', setup(b) {
    b.onResolve({ filter: /\/(api|usePageRefresh|UiToolbar|UiCustomText)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ loader: 'js', contents:
      args.path === 'api' ? 'export const veraApi = globalThis.__spaHistoryApi;' :
      args.path === 'usePageRefresh' ? 'export default function Hook() {}' :
      args.path === 'UiCustomText' ? 'export default function Text({children}) { return children }' :
      'import React from "react"; export default function Toolbar({children,...props}) { return React.createElement("div",props,children) }',
    }))
  } }],
})
const sections = presets => Object.fromEntries(['pending', 'invoices', 'reports', 'history'].map(key => [key, [...presets]]))
const capabilities = (presets = ['today']) => ({
  customers_view: true, invoice_view: true, pending_view: true, paid_invoice_view: true, reports_view: true, export: true,
  date_filters: { version: 1, server_today: '2026-10-10', sections: sections(presets) },
})
const user = id => ({ id, role: 'letan', permissions: {
  live_tour_customers_view: true, live_tour_pending_view: true, live_tour_invoice_view: true,
  live_tour_paid_invoice_view: true, live_tour_reports_view: true, live_tour_export: true,
  live_tour_view: false, live_tour_payment: false, live_tour_customers_edit: false,
} })
const detail = (caps = capabilities(), label = 'Authorized service') => ({
  customer: { id: 'customer-1', name: 'Customer one' }, capabilities: caps,
  summary: { invoice_count: 1, total_revenue: 100, combo_remaining_units: 3 },
  services: [{ id: 'service-1', service: label, business_date: '2026-10-10', price: 100 }],
  combo_purchases: [{ id: 'combo-1', combo_name: 'Combo balance retained', remaining: 3 }],
  pending: [{ id: 'pending-1', created_at: '2026-10-10', entries: [{ service: 'Authorized pending' }] }],
})
function deferred() { let resolve, reject; const promise = new Promise((done, fail) => { resolve = done; reject = fail }); return { promise, resolve, reject } }

async function fixture({ response = detail(), initialUser = user('account-1') } = {}) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true, url: 'https://test.invalid' })
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true }
  const calls = { history: [], exports: [], pageReads: 0 }
  let nextHistory, nextExport, currentUser = initialUser
  const api = {
    spaCustomers: async () => { calls.pageReads++; return { revision: 1, can_export: true, customers: [{ id: 'customer-1', name: `Customer ${currentUser.id}`, combo_purchases: [] }] } },
    liveTourCustomerHistory: (customerId, query, options) => {
      calls.history.push({ customerId, query, signal: options.signal })
      const pending = nextHistory; nextHistory = null
      return pending ? pending.promise : Promise.resolve(structuredClone(response))
    },
    exportLiveTourExcel: (kind, query, options) => {
      calls.exports.push({ kind, query, signal: options.signal })
      const pending = nextExport; nextExport = null
      return pending ? pending.promise : Promise.resolve()
    },
  }
  const globals = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true, __spaHistoryApi: api }
  const saved = Object.fromEntries(Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, writable: true, configurable: true })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(dom.window.document.querySelector('#root'))
  const render = () => root.render(React.createElement(module.exports.default, { user: currentUser, mode: 'customers' }))
  await act(async () => render())
  const dialog = () => dom.window.document.querySelector('.spa-editor')
  const button = (text, scope = dom.window.document) => [...scope.querySelectorAll('button')].find(node => node.textContent.trim() === text)
  const select = () => dialog()?.querySelector('select[aria-label="Khoảng ngày lịch sử khách hàng"]')
  return {
    doc: dom.window.document, calls, dialog, button, select,
    response(value) { response = value },
    holdHistory() { nextHistory = deferred(); return nextHistory },
    holdExport() { nextExport = deferred(); return nextExport },
    async open() { await act(async () => button('Lịch sử').click()) },
    async click(text, scope) { await act(async () => button(text, scope).click()) },
    async preset(value) { await act(async () => { select().value = value; select().dispatchEvent(new dom.window.Event('change', { bubbles: true })) }) },
    async resolve(pending, value) { await act(async () => { pending.resolve(value) }) },
    async reject(pending, error) { await act(async () => { pending.reject(error) }) },
    async rerender(nextUser) { currentUser = nextUser; await act(async () => render()) },
    async input(label, value, type = 'text') {
      const node = [...dialog().querySelectorAll(`input[type="${type}"]`)].find(item => item.getAttribute('aria-label') === label)
      assert.ok(node, label)
      await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(node, value)
        node.dispatchEvent(new dom.window.Event(type === 'date' ? 'change' : 'input', { bubbles: true }))
      })
    },
    async closeDialog() { await act(async () => dialog().querySelector('button[aria-label="Đóng"]').click()) },
    async close() { await act(async () => root.unmount()); dom.window.close(); for (const [key, descriptor] of Object.entries(saved)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] } },
  }
}

test('customer history uses the server union and exports only an explicit common authorized preset', async () => {
  const f = await fixture()
  try {
    assert.equal(f.button('Thêm khách hàng').disabled, true, 'date read access never enables payments')
    await f.open()
    assert.deepEqual(f.calls.history[0].query, {})
    assert.match(f.dialog().textContent, /Authorized service/)
    assert.deepEqual([...f.select().options].map(option => option.value), ['', 'today'])
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
    await f.preset('today')
    assert.deepEqual(f.calls.history.at(-1).query, { preset: 'today', date_from: '2026-10-10', date_to: '2026-10-10', date: '' })
    await f.click('Xuất excel', f.dialog())
    assert.deepEqual(f.calls.exports[0].query, { customer_id: 'customer-1', ...f.calls.history.at(-1).query })
    assert.equal(f.calls.exports[0].kind, 'customer_detail')
    assert.equal(f.calls.exports[0].signal.aborted, false)
    await f.closeDialog()
    await f.click('Xuất excel')
    assert.equal(f.calls.exports.at(-1).kind, 'customers')
    assert.deepEqual(f.calls.exports.at(-1).query, {}, 'ordinary customer directory export keeps existing semantics')
  } finally { await f.close() }
})

test('disjoint grants retain the default authorized history and disable detailed export', async () => {
  const caps = capabilities()
  caps.date_filters.sections.invoices = ['yesterday']
  caps.date_filters.sections.reports = ['month']
  const f = await fixture({ response: detail(caps) })
  try {
    await f.open()
    assert.equal(f.select().options.length, 1)
    assert.deepEqual(f.calls.history[0].query, {})
    assert.match(f.dialog().textContent, /Authorized service/)
    assert.match(f.dialog().textContent, /Combo balance retained/)
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
  } finally { await f.close() }
})

test('account changes abort pending history and late responses cannot reopen the old customer', async () => {
  const f = await fixture()
  try {
    const pending = f.holdHistory()
    await f.open()
    const request = f.calls.history.at(-1)
    await f.rerender(user('account-2'))
    assert.equal(request.signal.aborted, true)
    assert.equal(f.dialog(), null)
    assert.doesNotMatch(f.doc.body.textContent, /Customer account-1/)
    await f.resolve(pending, detail(capabilities(), 'Old account private detail'))
    assert.equal(f.dialog(), null)
    assert.doesNotMatch(f.doc.body.textContent, /Old account private detail/)
    await f.open()
    assert.deepEqual(f.calls.history.at(-1).query, {})
  } finally { await f.close() }
})

test('profile revocation masks an open history and cancels its pending download', async () => {
  const f = await fixture()
  try {
    await f.open(); await f.preset('today')
    const pending = f.holdExport()
    await f.click('Xuất excel', f.dialog())
    const request = f.calls.exports.at(-1)
    const revoked = user('account-1')
    revoked.permissions.live_tour_paid_invoice_view = false
    await f.rerender(revoked)
    assert.equal(request.signal.aborted, true)
    assert.equal(f.dialog(), null)
    await f.resolve(pending)
    await f.open()
    assert.doesNotMatch(f.dialog().textContent, /Authorized service/)
    assert.match(f.dialog().textContent, /Combo balance retained/)
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
  } finally { await f.close() }
})

test('a refreshed server policy cancels downloads and suppresses revoked ledgers before the replacement load', async () => {
  const f = await fixture()
  try {
    await f.open(); await f.preset('today')
    const download = f.holdExport()
    await f.click('Xuất excel', f.dialog())
    const exportRequest = f.calls.exports.at(-1)
    const revoked = detail(capabilities([]), 'Revoked response service')
    f.response(revoked)
    const pending = f.holdHistory()
    await f.click('Làm mới lịch sử', f.dialog())
    assert.equal(exportRequest.signal.aborted, true)
    assert.doesNotMatch(f.dialog().textContent, /Authorized service/)
    await f.resolve(pending, revoked)
    assert.doesNotMatch(f.dialog().textContent, /Revoked response service|Authorized pending/)
    assert.match(f.dialog().textContent, /Combo balance retained/)
    assert.equal(f.select().value, '')
    assert.deepEqual(f.calls.history.at(-1).query, {})
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
    await f.resolve(download)
  } finally { await f.close() }
})

test('closing a loading dialog aborts it and repeated openings reject the earlier response', async () => {
  const f = await fixture()
  try {
    const pending = f.holdHistory()
    await f.open()
    const previous = f.calls.history.at(-1)
    await f.closeDialog()
    assert.equal(previous.signal.aborted, true)
    await f.open()
    await f.resolve(pending, detail(capabilities(), 'Earlier dialog service'))
    assert.match(f.dialog().textContent, /Authorized service/)
    assert.doesNotMatch(f.dialog().textContent, /Earlier dialog service/)
  } finally { await f.close() }
})

test('custom dates use dd-mm-yyyy and partial drafts hide rows and prevent exporting old dates', async () => {
  const f = await fixture({ response: detail(capabilities(['custom'])) })
  try {
    await f.open(); await f.preset('custom')
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
    const before = f.calls.history.length
    await f.input('Lịch Từ ngày lịch sử khách hàng', '2026-10-01', 'date')
    assert.equal(f.calls.history.length, before, 'both custom boundaries are required')
    await f.input('Lịch Đến ngày lịch sử khách hàng', '2026-10-10', 'date')
    assert.equal(f.dialog().querySelector('input[aria-label="Từ ngày lịch sử khách hàng"]').value, '01-10-2026')
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, false)
    await f.input('Từ ngày lịch sử khách hàng', '02-10')
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
    assert.doesNotMatch(f.dialog().textContent, /Authorized service/)
    assert.equal(f.calls.history.length, before + 1, 'partial input cannot submit the previously saved boundary')
  } finally { await f.close() }
})

test('a later date selection wins over an ignored aborted response', async () => {
  const f = await fixture({ response: detail(capabilities(['today', 'yesterday'])) })
  try {
    await f.open()
    const pending = f.holdHistory()
    await f.preset('today')
    const previous = f.calls.history.at(-1)
    f.response(detail(capabilities(['today', 'yesterday']), 'Newer selection service'))
    await f.preset('yesterday')
    assert.equal(previous.signal.aborted, true)
    await f.resolve(pending, detail(capabilities(), 'Older selection service'))
    assert.equal(f.select().value, 'yesterday')
    assert.match(f.dialog().textContent, /Newer selection service/)
    assert.doesNotMatch(f.dialog().textContent, /Older selection service/)
    await f.click('Xuất excel', f.dialog())
    assert.equal(f.calls.exports.at(-1).query.preset, 'yesterday')
    assert.equal(f.calls.exports.at(-1).query.date_from, '2026-10-09')
  } finally { await f.close() }
})

test('date grants alone cannot enable missing section reads or customer writes', async () => {
  const account = user('account-1')
  account.permissions.live_tour_paid_invoice_view = false
  account.permissions.live_tour_invoices_date_today = true
  const f = await fixture({ initialUser: account })
  try {
    await f.open()
    assert.doesNotMatch(f.dialog().textContent, /Authorized service/)
    assert.match(f.dialog().textContent, /Authorized pending/)
    assert.equal(f.select().options.length, 1)
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
    await f.closeDialog()
    assert.equal(f.button('Thêm khách hàng').disabled, true)
    assert.equal(f.button('Sửa').disabled, true)
  } finally { await f.close() }
})

test('ordinary customer export is aborted when the account changes', async () => {
  const f = await fixture()
  try {
    const pending = f.holdExport()
    await f.click('Xuất excel')
    const request = f.calls.exports.at(-1)
    assert.equal(request.kind, 'customers')
    await f.rerender(user('account-2'))
    assert.equal(request.signal.aborted, true)
    await f.resolve(pending)
    assert.match(f.doc.body.textContent, /Customer account-2/)
  } finally { await f.close() }
})

test('duplicate detailed downloads are blocked and closing the history aborts the running download', async () => {
  const f = await fixture()
  try {
    await f.open(); await f.preset('today')
    const pending = f.holdExport()
    await f.click('Xuất excel', f.dialog())
    assert.equal(f.calls.exports.length, 1)
    assert.equal(f.button('Đang xuất…', f.dialog()).disabled, true)
    await f.click('Đang xuất…', f.dialog())
    assert.equal(f.calls.exports.length, 1)
    const request = f.calls.exports[0]
    await f.closeDialog()
    assert.equal(request.signal.aborted, true)
    await f.resolve(pending)
    assert.equal(f.dialog(), null)
  } finally { await f.close() }
})

test('date-policy 403 adopts fresh capabilities and retries only the authorized default union', async () => {
  const f = await fixture()
  try {
    await f.open(); await f.preset('today')
    const denied = f.holdHistory()
    await f.click('Làm mới lịch sử', f.dialog())
    const fresh = capabilities(['yesterday'])
    f.response(detail(fresh, 'Fresh permitted union'))
    await f.reject(denied, Object.assign(Error('Date grant changed'), { status: 403, payload: { detail: { capabilities: fresh } } }))
    assert.deepEqual(f.calls.history.at(-1).query, {})
    assert.deepEqual([...f.select().options].map(option => option.value), ['', 'yesterday'])
    assert.match(f.dialog().textContent, /Fresh permitted union/)
    assert.doesNotMatch(f.dialog().textContent, /Authorized service/)
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
  } finally { await f.close() }
})

test('an ordinary read-parent 403 removes old details and requires an explicit retry', async () => {
  const f = await fixture()
  try {
    await f.open(); await f.preset('today')
    const denied = f.holdHistory()
    await f.click('Làm mới lịch sử', f.dialog())
    const count = f.calls.history.length
    await f.reject(denied, Object.assign(Error('Customer read access denied'), { status: 403 }))
    assert.equal(f.calls.history.length, count, 'a parent read denial must not automatically retry')
    assert.doesNotMatch(f.dialog().textContent, /Authorized service|Authorized pending|Combo balance retained/)
    assert.equal(f.select().disabled, true)
    assert.equal(f.button('Xuất excel', f.dialog()).disabled, true)
    await f.click('Làm mới lịch sử', f.dialog())
    assert.equal(f.calls.history.length, count + 1)
    assert.match(f.dialog().textContent, /Authorized service/)
  } finally { await f.close() }
})
