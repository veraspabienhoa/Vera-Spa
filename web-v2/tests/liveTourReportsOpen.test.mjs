import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { TOUR_DATE_PRESETS, tourDateRange } from '../src/lib/liveTourFilters.js'

// Keep the real page, detail loader, reports panel and revenue summary together.
// Mocking the summary missed the first render before the scoped request starts.
const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
dom.window.HTMLElement.prototype.scrollIntoView = function () {}
const { createRoot } = await import('react-dom/client')
const built = await build({
  stdin: { contents: "export { default as Page } from './src/pages/LiveTourPage.jsx'; export { default as Boundary } from './src/components/PageErrorBoundary.jsx'", resolveDir: process.cwd() },
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'api-only', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__reportsOpenApi' }))
  } }],
})
const allPresets = TOUR_DATE_PRESETS.map(([id]) => id)
const today = tourDateRange('today').date_from
const yesterday = tourDateRange('yesterday').date_from
const money = value => `${Number(value).toLocaleString('vi-VN')} đ`
const totals = { totalRevenue: 987654321, serviceRevenue: 980000000, tip: 7654321, invoiceCount: 512 }
function capabilities(presets = allPresets, modern = true) {
  return { reports_view: true, export: true, paid_invoice_view: true,
    ...(modern ? { date_filters: { version: 1, server_today: today, sections: { pending: [], invoices: [], reports: presets, history: [] } } } : {}) }
}
function response({ summary = totals, rows = [{ id: 'r1', employee_name: 'SYNTHETIC', total: 123, tip: 3, business_date: yesterday }], caps = capabilities(), page = 1, total = 512 } = {}) {
  return { revision: 7, capabilities: caps, page, page_size: 50, pages: Math.max(1, Math.ceil(total / 50)), total,
    data: { report_rows: rows, report_totals: summary, state: { reports: rows, invoices: [] } } }
}
async function fixture(role = 'admin', caps = capabilities()) {
  window.sessionStorage.clear(); window.localStorage.clear()
  const reads = [], mutations = []
  const board = { revision: 7, columns: ['STT', 'Tên nhân viên'], records: [], capabilities: caps, state: { employees: [] } }
  globalThis.__reportsOpenApi = {
    liveTour: async () => structuredClone(board),
    liveTourCollection: (panel, query, options) => new Promise((resolve, reject) => reads.push({ panel, query, options, resolve, reject })),
    liveTourAction: async (...args) => { mutations.push(args); throw Error('No production or fixture writes expected') },
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
  const { Page, Boundary } = module.exports
  const root = createRoot(document.querySelector('#root'))
  const user = { id: `synthetic-${role}`, employee_username: `synthetic-${role}`, role, permissions: { live_tour_view: true, live_tour_reports_view: true, live_tour_export: true } }
  const render = next => act(async () => root.render(React.createElement(Boundary, { page: 'live-tour' }, React.createElement(Page, { user: next }))))
  await render(user)
  return { reads, mutations, board, user, render,
    wait: () => act(() => new Promise(resolve => setTimeout(resolve, 220))),
    resolve: value => act(async () => reads.at(-1).resolve(value)),
    reject: error => act(async () => reads.at(-1).reject(error)),
    close: () => act(() => root.unmount()) }
}
async function click(label, scope = document) {
  const node = [...scope.querySelectorAll('button')].find(button => button.textContent.trim() === label)
  assert.ok(node, `Missing button ${label}`)
  await act(async () => node.click())
}
const summary = () => document.querySelector('.live-tour-panel-body .tour-revenue-summary')
const healthy = () => assert.doesNotMatch(document.body.textContent, /PAGE_RENDER|Không mở được chức năng này/)
const open = () => click('Báo cáo', document.querySelector('.tour-heading-actions'))

for (const role of ['admin', 'quanly', 'letan']) for (const modern of [true, false]) {
  test(`toolbar report opens safely before and after the scoped read: ${role}, ${modern ? 'versioned' : 'legacy'} capabilities`, async () => {
    const caps = capabilities(allPresets, modern)
    const f = await fixture(role, caps)
    try {
      await open()
      healthy()
      assert.equal(summary(), null, 'no cleared/board/page-local totals before an authorized response')
      await f.wait()
      assert.equal(f.reads.length, 1)
      assert.equal(f.reads[0].panel, 'reports')
      assert.equal(f.reads[0].query.preset, 'yesterday')
      assert.ok(f.reads[0].options.signal instanceof AbortSignal)
      assert.equal(summary(), null)
      await f.resolve(response({ caps }))
      healthy()
      assert.ok(summary())
      assert.match(summary().textContent, new RegExp(money(totals.totalRevenue)))
      assert.match(summary().textContent, /512/)
      assert.equal(document.querySelectorAll('.live-tour-panel-body .live-tour-data-card').length, 1)
      assert.deepEqual(f.mutations, [])
    } finally { await f.close() }
  })
}

test('empty authorized report renders real zero totals; filter changes wait for their own full totals', async () => {
  const f = await fixture()
  try {
    await open(); await f.wait()
    await f.resolve(response({ summary: { totalRevenue: 0, serviceRevenue: 0, tip: 0, invoiceCount: 0 }, rows: [], total: 0 }))
    healthy()
    assert.match(document.body.textContent, /Chưa có số liệu báo cáo/)
    assert.match(summary().textContent, /0 đ/)
    await click('Hôm nay', document.querySelector('.report-date-buttons'))
    healthy()
    assert.equal(summary(), null, 'old empty response is not the new filter result')
    await f.wait(); assert.equal(f.reads.at(-1).query.preset, 'today')
    await f.resolve(response())
    assert.match(summary().textContent, new RegExp(money(totals.totalRevenue)))
    await click('Trang sau', document.querySelector('.live-tour-pagination'))
    healthy(); assert.equal(summary(), null)
    await f.wait(); assert.equal(f.reads.at(-1).query.page, 2)
    await f.resolve(response({ page: 2 }))
    assert.match(summary().textContent, new RegExp(money(totals.totalRevenue)))
  } finally { await f.close() }
})

test('failed report reads keep the error visible and never render cleared aggregates', async () => {
  const f = await fixture()
  try {
    await open(); await f.wait()
    await f.reject(Object.assign(new Error('Synthetic report unavailable'), { status: 503 }))
    healthy(); assert.equal(summary(), null)
    assert.match(document.querySelector('.live-tour-pagination [role="alert"]').textContent, /Synthetic report unavailable/)
    await click('Hôm nay', document.querySelector('.report-date-buttons')); await f.wait()
    await f.resolve(response())
    healthy(); assert.ok(summary())
  } finally { await f.close() }
})

test('revoked report date permissions hide old totals, cancel the pending request and suppress late data', async () => {
  const f = await fixture('letan', capabilities(['today', 'week']))
  try {
    await open(); await f.wait(); await f.resolve(response({ caps: capabilities(['today', 'week']) }))
    assert.ok(summary())
    await click('Tuần này', document.querySelector('.report-date-buttons')); await f.wait()
    const pending = f.reads.at(-1)
    const denied = Object.fromEntries(allPresets.map(preset => [`live_tour_reports_date_${preset.replaceAll('-', '_')}`, false]))
    await f.render({ ...f.user, permissions: { ...f.user.permissions, ...denied } })
    healthy(); assert.equal(summary(), null)
    assert.equal(pending.options.signal.aborted, true)
    await act(async () => pending.resolve(response({ rows: [{ id: 'late', employee_name: 'LATE-DENIED', total: 12 }], caps: capabilities(['today', 'week']) })))
    await f.wait()
    assert.equal(f.reads.length, 2)
    assert.doesNotMatch(document.body.textContent, /LATE-DENIED|SYNTHETIC/)
  } finally { await f.close() }
})

test('all denied report presets open a permission message without any report request or export', async () => {
  const f = await fixture('quanly', capabilities([]))
  try {
    await open(); await f.wait()
    healthy(); assert.equal(summary(), null); assert.equal(f.reads.length, 0)
    assert.match(document.body.textContent, /Tài khoản chưa được cấp bộ lọc thời gian/)
    assert.equal(document.querySelector('.live-tour-panel-body'), null)
  } finally { await f.close() }
})


test('leaving and reopening reports cancels the abandoned read and never shows its late result', async () => {
  const f = await fixture()
  try {
    await open(); await f.wait()
    const abandoned = f.reads.at(-1)
    await click('Hóa đơn đã thanh toán', document.querySelector('.tour-heading-actions'))
    assert.equal(abandoned.options.signal.aborted, true)
    await open(); healthy(); assert.equal(summary(), null)
    await f.wait(); assert.equal(f.reads.length, 2)
    await act(async () => abandoned.resolve(response({ rows: [{ id: 'late', employee_name: 'ABANDONED-REPORT', total: 12 }] })))
    healthy(); assert.equal(summary(), null); assert.doesNotMatch(document.body.textContent, /ABANDONED-REPORT/)
    await f.resolve(response())
    healthy(); assert.ok(summary())
    await open(); healthy()
    assert.ok(summary(), 'repeated click keeps the current authorized result')
    assert.deepEqual(f.mutations, [])
  } finally { await f.close() }
})
