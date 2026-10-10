import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { answerDialogs } from './dialogAnswers.mjs'

const directory = fileURLToPath(new URL('../', import.meta.url))
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/PayrollPageEnhanced.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react-dom', 'react/jsx-runtime'], loader: { '.css': 'empty' },
  define: { 'import.meta.env': '{"VITE_VERA_API_BASE_URL":"https://api.invalid"}' },
  plugins: [{ name: 'auth-fixture', setup(builder) {
    builder.onResolve({ filter: /\/supabase$/ }, () => ({ path: 'auth', namespace: 'fixture' }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const getCurrentSession=async()=>({access_token:window.payrollFixtureToken || "synthetic"});export const isSupabaseConfigured=false;export const refreshCurrentSession=getCurrentSession;export const supabase=null' }))
  } }],
})
const payrollRows = count => Array.from({ length: count }, (_, index) => ({
  'Tên Hệ thống': `Employee ${String(index + 1).padStart(4, '0')}`, 'Họ và tên': `Full name ${index + 1}`,
  Email: `employee${index + 1}@example.test`, 'Mã bản lưu': 'Kỳ 1 - Tháng 10/2026',
  'Từ ngày': '2026-10-01', 'Đến ngày': '2026-10-15', 'Tiền Lương': 1000,
  'Số tiền thực nhận': 1000, __employment_status: 'Đang làm việc',
}))
const draftFor = rows => ({ rows, period_label: 'Kỳ 1 - Tháng 10/2026', start: '2026-10-01', end: '2026-10-15', saved_at: '2026-10-10T01:00:00Z', saved_by: 'admin' })
const response = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
const countReads = (requests, path) => requests.filter(request => request.url.pathname === path && (request.options.method || 'GET') === 'GET').length
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }

async function fixture({ records = [], draft = null, savedBatches = [], route, user = { role: 'admin', id: 'account-a' } } = {}) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
  const requests = [], downloads = []
  const values = {
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator, URL: dom.window.URL,
    IS_REACT_ACT_ENVIRONMENT: true,
    fetch: async (url, options = {}) => {
      const parsed = new URL(url); requests.push({ url: parsed, options })
      if (route) { const result = await route(parsed, options); if (result !== undefined) return result }
      let body = {}
      if (parsed.pathname === '/v2/payroll/history') body = { records, batches: ['Kỳ 1 - Tháng 10/2026', 'Other batch'], employees: ['Employee 0001', 'Employee 0101'] }
      if (parsed.pathname === '/v2/payroll/draft') body = { draft }
      if (parsed.pathname === '/v2/payroll/saved-batches') body = { saved_batches: savedBatches }
      if (parsed.pathname === '/v2/payroll/config') body = { config: { default_living_expense: 150000, default_locker_support: 80000, leader_responsibility_allowance: 0 } }
      if (parsed.pathname === '/v2/payroll/email') body = { sent: JSON.parse(options.body).rows.map(row => row['Tên Hệ thống']), failed: [] }
      return response(body)
    },
  }
  const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { value, configurable: true })
  URL.createObjectURL = () => 'blob:synthetic-export'
  URL.revokeObjectURL = () => {}
  window.HTMLAnchorElement.prototype.click = function () { downloads.push(this.download) }
  window.confirm = () => true
  const stopAnswering = answerDialogs(window)
  const mod = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.getElementById('root'))
  const render = async nextUser => {
    window.payrollFixtureToken = nextUser.id || 'synthetic'
    await act(async () => root.render(React.createElement(mod.exports.default, { user: nextUser, activeTab: 'history' })))
  }
  await render(user)
  return {
    dom, root, requests, downloads, render,
    async change(input, value) {
      await act(async () => {
        const prototype = input.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype
        Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value)
        input.dispatchEvent(new window.Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
      })
    },
    async click(text, scope = document) {
      const button = [...scope.querySelectorAll('button')].find(item => item.textContent.trim() === text)
      assert.ok(button, `Missing button: ${text}`)
      await act(async () => button.click())
    },
    async close() {
      await act(async () => root.unmount()); stopAnswering(); dom.window.close()
      for (const [key, descriptor] of Object.entries(saved)) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]
      }
    },
  }
}
const historyPanel = () => document.querySelector('.payroll-history-panel')
const draftPanel = () => document.querySelector('.payroll-draft-panel')
const historyTable = () => historyPanel().querySelector('.payroll-history-desktop table')
const pager = panel => panel.querySelector('.table-pager')

test('3000 payroll history rows mount 100 per layout, retain selected rows across pages, and export all filter results', async () => {
  const records = payrollRows(3000)
  const f = await fixture({ records })
  try {
    await f.click('Hiện lịch sử')
    assert.equal(historyTable().tBodies[0].rows.length, 100)
    assert.equal(historyPanel().querySelectorAll('.payroll-history-mobile article').length, 100)
    assert.match(pager(historyPanel()).textContent, /Trang 1 \/ 30/)
    assert.match(historyPanel().querySelector('.payroll-history-metrics').textContent, /3000.*3\.000\.000đ/)
    await act(async () => historyTable().querySelector('input').click())
    await f.click('Trang sau', pager(historyPanel()))
    assert.match(historyTable().tBodies[0].rows[0].textContent, /Employee 0101/)
    await act(async () => historyTable().querySelector('input').click())
    await f.click('Trang trước', pager(historyPanel()))
    assert.equal(historyTable().querySelector('input').checked, true)
    await f.click('Gửi email (2)', historyPanel())
    const emailed = f.requests.filter(request => request.url.pathname === '/v2/payroll/email').flatMap(request => JSON.parse(request.options.body).rows)
    assert.deepEqual(emailed.map(row => row['Tên Hệ thống']), ['Employee 0001', 'Employee 0101'])
    await act(async () => historyPanel().querySelector('.payroll-select-all input').click())
    assert.match(historyPanel().querySelector('.payroll-history-actions').textContent, /Gửi email \(3000\)/)
    await f.click('Trang sau', pager(historyPanel()))
    assert.equal(historyTable().querySelector('input').checked, true)
    assert.equal(countReads(f.requests, '/v2/payroll/history'), 1, 'paging does not refetch the unbounded endpoint')
    await f.click('Excel lịch sử', historyPanel())
    const exported = f.requests.find(request => request.url.pathname.endsWith('/history/export.xlsx'))
    assert.equal(exported.url.searchParams.has('page'), false)
    assert.equal(exported.url.searchParams.has('limit'), false)
    assert.equal(f.downloads.length, 1)
    await f.change(historyPanel().querySelector('input[type="search"]'), 'Employee 2999')
    assert.equal(historyTable().tBodies[0].rows.length, 1)
    assert.match(historyTable().textContent, /Employee 2999/)
    assert.match(historyPanel().querySelector('.payroll-history-metrics').textContent, /1.*1\.000đ/)
    await f.click('Xóa lọc', historyPanel())
    assert.match(pager(historyPanel()).textContent, /Trang 1 \/ 30/)
    assert.equal(historyTable().querySelector('input').checked, false, 'existing filter changes still clear history selection')
    assert.equal(countReads(f.requests, '/v2/payroll/history'), 1)
  } finally { await f.close() }
})

test('draft paging preserves unsaved money and selections, with full totals and full draft export', async () => {
  const rows = payrollRows(205), f = await fixture({ draft: draftFor(rows) })
  try {
    const table = () => draftPanel().querySelector('.payroll-desktop-table table')
    assert.equal(table().tBodies[0].rows.length, 100)
    assert.equal(draftPanel().querySelectorAll('.payroll-mobile-list article').length, 100)
    assert.match(draftPanel().querySelector('.panel-title-row').textContent, /205\.000đ/)
    await f.change(table().querySelector('.vera-money-input'), '500')
    await act(async () => table().querySelector('input[type="checkbox"]').click())
    await f.click('Trang sau', pager(draftPanel()))
    const editing = table().querySelector('.vera-money-input')
    editing.focus()
    await f.change(editing, '700')
    assert.equal(document.activeElement, editing, 'typing preserves the active input instead of remounting its row')
    assert.match(pager(draftPanel()).textContent, /Trang 2 \/ 3/)
    assert.match(table().tBodies[0].rows[0].textContent, /Employee 0101/)
    await act(async () => table().querySelector('input[type="checkbox"]').click())
    await f.click('Trang trước', pager(draftPanel()))
    assert.equal(table().querySelector('.vera-money-input').value, '500')
    assert.equal(table().querySelector('input[type="checkbox"]').checked, false)
    assert.match(draftPanel().querySelector('.panel-title-row').textContent, /206\.200đ/)
    assert.match(draftPanel().querySelector('.panel-title-row').textContent, /Gửi email \(203\)/)
    await f.click('Trang sau', pager(draftPanel()))
    await f.click('Xuất excel', draftPanel())
    const exported = f.requests.find(request => request.url.pathname === '/v2/payroll/draft/export.xlsx')
    const body = JSON.parse(exported.options.body)
    assert.equal(body.rows.length, 205)
    assert.equal(body.rows[0]['Tiền Hỗ Trợ Hoàn Lại'], 500)
    assert.equal(body.rows[0]['Số tiền thực nhận'], 1500)
    assert.equal(body.rows[100]['Tên Hệ thống'], 'Employee 0101')
    assert.equal(body.rows[100]['Tiền Hỗ Trợ Hoàn Lại'], 700)
    assert.equal(countReads(f.requests, '/v2/payroll/draft'), 1, 'an exact draft hit does not fetch the same draft again with fallback enabled')
    await f.change(draftPanel().querySelector('input[type="search"]'), 'Employee 0205')
    assert.equal(table().tBodies[0].rows.length, 1)
    await f.click('Xóa lọc', draftPanel())
    assert.match(pager(draftPanel()).textContent, /Trang 1 \/ 3/)
    assert.equal(table().querySelector('.vera-money-input').value, '500')
  } finally { await f.close() }
})

test('history batch and employee filters only refetch history and preserve unsaved configuration', async () => {
  const f = await fixture({ records: payrollRows(105), draft: draftFor(payrollRows(1)) })
  try {
    const stablePaths = ['/v2/payroll/config', '/v2/payroll/accumulation-refunds', '/v2/payroll/obligations', '/v2/payroll/saved-batches', '/v2/payroll/draft']
    for (const path of stablePaths) assert.equal(countReads(f.requests, path), 1, path)
    await f.click('Hiện cài đặt')
    const configInput = document.querySelector('.payroll-config-grid input')
    await f.change(configInput, '999999')
    await f.click('Hiện lịch sử')
    await f.click('Trang sau', pager(historyPanel()))
    await f.change(historyPanel().querySelectorAll('select')[0], 'Other batch')
    await f.change(historyPanel().querySelectorAll('select')[1], 'Employee 0101')
    assert.equal(countReads(f.requests, '/v2/payroll/history'), 3)
    assert.match(pager(historyPanel()).textContent, /Trang 1 \/ 2/)
    for (const path of stablePaths) assert.equal(countReads(f.requests, path), 1, `${path} must not follow history filters`)
    assert.equal(configInput.value, '999.999')
    assert.deepEqual(f.requests.filter(request => request.url.pathname === '/v2/payroll/history').map(request => Object.fromEntries(request.url.searchParams)), [
      {}, { batch: 'Other batch' }, { batch: 'Other batch', search: 'Employee 0101' },
    ])
    await f.change(configInput, '150000')
    await act(async () => window.dispatchEvent(new window.Event('vera:page-refresh')))
    for (const path of stablePaths.filter(path => !path.endsWith('/draft'))) assert.equal(countReads(f.requests, path), 2, `explicit refresh retains ${path}`)
  } finally { await f.close() }
})

test('latest draft lookup waits for a confirmed miss and never replaces the selected empty period', async () => {
  const exact = deferred(), oldDraft = draftFor(payrollRows(1))
  const f = await fixture({ route: url => url.pathname === '/v2/payroll/draft'
    ? url.searchParams.has('latest_if_missing') ? response({ draft: oldDraft, fallback_used: true }) : exact.promise
    : undefined })
  try {
    assert.equal(countReads(f.requests, '/v2/payroll/draft'), 1)
    assert.equal(f.requests.some(request => request.url.searchParams.has('latest_if_missing')), false)
    await act(async () => exact.resolve(response({ draft: null })))
    assert.equal(countReads(f.requests, '/v2/payroll/draft'), 2)
    assert.equal(draftPanel(), null, 'fallback availability must not load an older payroll implicitly')
    assert.equal(document.querySelector('[data-ui-key="payroll-restore-saved-draft"]').classList.contains('primary-button'), true)
  } finally { await f.close() }
})

test('failed exact draft request does not invoke the more expensive fallback lookup', async () => {
  const f = await fixture({ route: url => url.pathname === '/v2/payroll/draft' ? response({ detail: 'Synthetic draft failure' }, 400) : undefined })
  try {
    assert.equal(countReads(f.requests, '/v2/payroll/draft'), 1)
    assert.match(document.querySelector('.error-box').textContent, /Synthetic draft failure/)
    assert.equal(f.requests.some(request => request.url.searchParams.has('latest_if_missing')), false)
  } finally { await f.close() }
})

test('obsolete period responses cannot launch a latest-draft lookup or overwrite the current draft', async () => {
  const stale = deferred(); let first = true
  const f = await fixture({ route: url => {
    if (url.pathname !== '/v2/payroll/draft') return undefined
    if (first) { first = false; return stale.promise }
    return response({ draft: draftFor(payrollRows(1)) })
  } })
  try {
    await f.change(document.querySelector('input[type="month"]'), '2025-01')
    assert.ok(draftPanel())
    await act(async () => stale.resolve(response({ draft: null })))
    assert.equal(countReads(f.requests, '/v2/payroll/draft'), 2)
    assert.equal(f.requests.some(request => request.url.searchParams.has('latest_if_missing')), false)
    assert.ok(draftPanel())
    assert.equal(document.querySelector('input[type="month"]').value, '2025-01')
  } finally { await f.close() }
})

test('bounded payroll rendering is separate from full financial/export collections in source', () => {
  const source = readFileSync(`${directory}src/pages/PayrollPageEnhanced.jsx`, 'utf8')
  assert.equal((source.match(/historyPage\.rows\.map/g) || []).length, 2)
  assert.equal((source.match(/draftPage\.rows\.map/g) || []).length, 2)
  assert.match(source, /rows: draft\.rows/)
  assert.match(source, /historyKeys = useMemo\(\(\) => visibleHistory\.map/)
  assert.match(source, /visibleHistory\.reduce/)
  assert.doesNotMatch(source, /Promise\.all\(\[veraApi\.payrollDraft/)
})

test('saved-batch cards are bounded and a later page opens the exact saved period', async () => {
  const savedBatches = Array.from({ length: 105 }, (_, index) => ({ batch: `Batch ${index + 1}`, employee_count: 2, total_net: 1000 }))
  const f = await fixture({ savedBatches })
  try {
    await f.click('Hiện lịch sử')
    const savedPager = document.querySelector('nav[aria-label="Phân trang các kỳ lương đã lưu"]')
    assert.equal(document.querySelectorAll('.saved-payroll-card').length, 50)
    assert.match(savedPager.textContent, /Trang 1 \/ 3/)
    await f.click('Trang sau', savedPager)
    assert.equal(document.querySelector('.saved-payroll-card h3').textContent, 'Batch 51')
    await f.click('Xem chi tiết', document.querySelector('.saved-payroll-card'))
    const historyRead = f.requests.filter(request => request.url.pathname === '/v2/payroll/history').at(-1)
    assert.equal(historyRead.url.searchParams.get('batch'), 'Batch 51')
    assert.equal(countReads(f.requests, '/v2/payroll/saved-batches'), 1)
    assert.match(savedPager.textContent, /Trang 2 \/ 3/)
  } finally { await f.close() }
})

test('same-grant account changes immediately clear prior data and ignore outstanding old-account reads', async () => {
  const oldPending = deferred(), nextPending = deferred()
  let refreshOld = false
  const rowA = { ...payrollRows(1)[0], 'Tên Hệ thống': 'Private account A' }
  const rowB = { ...payrollRows(1)[0], 'Tên Hệ thống': 'Private account B' }
  const f = await fixture({ route: async (url, options) => {
    const account = new Headers(options.headers).get('Authorization')
    const old = account === 'Bearer account-a'
    if (old && refreshOld) await oldPending.promise
    if (!old) await nextPending.promise
    if (url.pathname === '/v2/payroll/history') return response({ records: [old ? rowA : rowB], batches: [], employees: [] })
    if (url.pathname === '/v2/payroll/draft') return response({ draft: draftFor([old ? rowA : rowB]) })
    if (url.pathname === '/v2/payroll/config') return response({ config: { default_living_expense: old ? 150000 : 250000, default_locker_support: 80000 } })
    return response({})
  } })
  try {
    assert.match(document.body.textContent, /Private account A/)
    refreshOld = true
    await act(async () => window.dispatchEvent(new window.Event('vera:page-refresh')))
    await f.render({ role: 'admin', id: 'account-b' })
    assert.doesNotMatch(document.body.textContent, /Private account A/)
    assert.equal(draftPanel(), null)
    assert.equal(historyTable().tBodies[0].rows.length, 0)
    await act(async () => nextPending.resolve())
    assert.match(document.body.textContent, /Private account B/)
    await f.click('Hiện cài đặt')
    const configInput = document.querySelector('.payroll-config-grid input')
    assert.equal(configInput.value, '250.000')
    await f.change(configInput, '777777')
    await act(async () => oldPending.resolve())
    assert.doesNotMatch(document.body.textContent, /Private account A/)
    assert.match(document.body.textContent, /Private account B/)
    assert.equal(configInput.value, '777.777')
    assert.equal(countReads(f.requests, '/v2/payroll/draft'), 2)
    assert.equal(countReads(f.requests, '/v2/payroll/accumulation-refunds'), 2, 'an old account refresh must not start more support reads after unmount')
  } finally { oldPending.resolve(); nextPending.resolve(); await f.close() }
})
