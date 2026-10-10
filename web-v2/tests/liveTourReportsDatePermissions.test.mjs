import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { EMPTY_REPORT_PAGE, reportReadQuery } from '../src/lib/liveTourReportPage.js'
import { tourDateRange, TOUR_DATE_PRESETS } from '../src/lib/liveTourFilters.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, sessionStorage: { value: dom.window.sessionStorage, configurable: true },
  IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LiveTourReportsPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'date-permissions-api-fixture', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__reportsDateApi;', loader: 'js' }))
  } }],
})
const all = TOUR_DATE_PRESETS.map(([id]) => id)
const today = tourDateRange('today').date_from
const permissionFlags = (section, presets) => Object.fromEntries(all.map(preset => [`live_tour_${section}_date_${preset.replaceAll('-', '_')}`, presets.includes(preset)]))
const operator = (reports = all, history = all, patch = {}) => ({ id: 'operator', role: 'letan', permissions: {
  live_tour_reports_view: true, live_tour_view: true, live_tour_history_view: true, live_tour_export: true,
  ...permissionFlags('reports', reports), ...permissionFlags('history', history), ...patch,
} })
const capabilities = (reports = all, history = all, serverToday = today) => ({
  reports_view: true, history_view: true, export: true, reports_edit: true, reports_delete: true,
  paid_invoice_view: true, date_filters: { version: 1, server_today: serverToday, sections: { pending: [], invoices: [], reports, history } },
})
function page(caps = capabilities(), marker = 'CURRENT') {
  const row = { id: marker, invoice_id: `invoice-${marker}`, bill_no: `BILL-${marker}`, employee_name: 'An',
    business_date: today, effective_at: `${today}T09:00:00+07:00`, service: 'Body', total: 100, tip: 10 }
  return { ...EMPTY_REPORT_PAGE, revision: 7, rows: [row], total: 1, capabilities: caps,
    invoices: [{ ...row, id: row.invoice_id, entries: [{ employee_name: 'An', service: 'Body', price: 100 }] }] }
}
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
async function mount(api, user = operator()) {
  sessionStorage.clear()
  globalThis.__reportsDateApi = api
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(document.querySelector('#root'))
  const render = user => act(async () => root.render(React.createElement(module.exports.default, { user })))
  await render(user)
  return { root, render, close: () => act(() => root.unmount()) }
}
const button = label => [...document.querySelectorAll('button')].find(node => node.textContent === label)
async function click(label) {
  assert.ok(button(label), `Missing button ${label}`)
  await act(async () => button(label).click())
}
async function input(field, value) {
  assert.ok(field)
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(field, value)
    field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    field.dispatchEvent(new dom.window.FocusEvent('blur', { bubbles: true }))
    field.dispatchEvent(new dom.window.FocusEvent('focusout', { bubbles: true }))
  })
}

test('report queries retain the explicit date permission selector', () => {
  for (const preset of all) assert.equal(reportReadQuery({ preset }, 'revenue', 'all').preset, preset)
})

test('a today-only report permission uses the server day and hides every disallowed date control', async () => {
  const queries = [], exports = []
  const user = operator(['today'], [], { live_tour_view: false, live_tour_history_view: false })
  const fixture = await mount({
    liveTourReports: async query => { queries.push(query); return page(capabilities(['today'], [], '2026-01-01')) },
    exportLiveTourExcel: async (kind, query) => exports.push({ kind, query }),
  }, user)
  try {
    assert.ok(queries.length >= 1)
    assert.equal(queries.at(-1).preset, 'today')
    assert.equal(queries.at(-1).date_from, '2026-01-01')
    assert.equal(queries.at(-1).date_to, '2026-01-01')
    for (const [id, label] of TOUR_DATE_PRESETS) assert.equal(Boolean(button(label)), id === 'today', label)
    assert.equal(document.querySelector('input[aria-label="Lọc ngày hóa đơn"]'), null)
    assert.ok(button('Lịch sử Live Tour'))
    await click('Xuất excel')
    assert.equal(exports[0].query.preset, 'today')
    assert.equal(exports[0].query.date_from, '2026-01-01')
  } finally { await fixture.close() }
})

test('no date grants suppress every report read and export rather than falling back to all time', async () => {
  let reads = 0
  const fixture = await mount({ liveTourReports: async () => { reads++; return page() } }, operator([], []))
  try {
    assert.equal(reads, 0)
    assert.equal(button('Xuất excel'), undefined)
    assert.equal(button('Chia sẻ số khách · PDF/PNG'), undefined)
    assert.match(document.body.textContent, /chưa được cấp bộ lọc ngày/)
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 0)
  } finally { await fixture.close() }
})

test('report board history shares report-authorized dates and preserves its export preset', async () => {
  const reports = [], history = [], exports = []
  const caps = capabilities(['today', 'month'], ['today', 'yesterday'])
  const fixture = await mount({
    liveTourReports: async query => { reports.push(query); return page(caps) },
    liveTourBoardHistory: async query => { history.push(query); return { rows: [], columns: [], capabilities: caps } },
    exportLiveTourBoardHistory: async query => exports.push(query),
  }, operator(['today', 'month'], ['today', 'yesterday']))
  try {
    await click('Tháng này')
    await click('Lịch sử Live Tour')
    assert.equal(history.at(-1).preset, 'month')
    await click('Hôm nay')
    await click('Xuất excel')
    assert.equal(exports[0].preset, 'today')
    await click('Doanh thu')
    assert.equal(reports.at(-1).preset, 'today')
    await click('Lịch sử Live Tour')
    assert.equal(history.at(-1).preset, 'today')
    const stored = [...Array(sessionStorage.length)].map((_, i) => sessionStorage.key(i))
    assert.ok(stored.some(key => key.endsWith(':operator:reports')))
    assert.ok(!stored.some(key => key.endsWith(':operator:history')), 'report snapshots must not overwrite the audit-panel date selection')
  } finally { await fixture.close() }
})

test('account changes synchronously hide previous rows and receipt while the fresh authorized read is pending', async () => {
  const pending = deferred(), queries = []
  let nextAccount = false
  const fixture = await mount({ liveTourReports: async query => {
    queries.push(query)
    return nextAccount ? pending.promise : page(capabilities(['today', 'month']), 'PRIVATE-OLD')
  } }, operator(['today', 'month']))
  try {
    await click('Tháng này')
    await act(async () => document.querySelector('[aria-label="Xem hóa đơn"]').click())
    assert.ok(document.querySelector('[role="dialog"]'))
    nextAccount = true
    await fixture.render({ ...operator(['today']), id: 'different' })
    assert.equal(queries.at(-1).preset, 'today')
    assert.equal(document.querySelector('[role="dialog"]'), null)
    assert.doesNotMatch(document.body.textContent, /PRIVATE-OLD/)
    await act(async () => pending.resolve(page(capabilities(['today']), 'NEW')))
    assert.match(document.body.textContent, /BILL-NEW/)
    assert.doesNotMatch(document.body.textContent, /PRIVATE-OLD/)
  } finally { await fixture.close() }
})

test('a server date revocation clears rows and prepared PDF/PNG reads, without another forbidden report request', async () => {
  let revoked = false, reads = 0
  const prepared = []
  const fixture = await mount({
    liveTourReports: async () => { reads++; return page(capabilities(revoked ? [] : ['today']), revoked ? 'FORBIDDEN' : 'ALLOWED') },
    readCustomerCountPdf: (filters, options) => { const task = deferred(); prepared.push({ ...task, filters, signal: options.signal }); return task.promise },
    readCustomerCountPng: (filters, options) => { const task = deferred(); prepared.push({ ...task, filters, signal: options.signal }); return task.promise },
  }, operator(['today']))
  try {
    await click('Chia sẻ số khách · PDF/PNG')
    assert.equal(prepared.length, 2)
    assert.ok(prepared.every(item => item.filters.preset === 'today'))
    revoked = true
    const before = reads
    await click('Làm mới')
    assert.equal(reads, before + 1)
    assert.ok(prepared.every(item => item.signal.aborted))
    assert.equal(document.querySelector('[role="dialog"]'), null)
    assert.equal(button('Xuất excel'), undefined)
    assert.doesNotMatch(document.body.textContent, /BILL-ALLOWED|BILL-FORBIDDEN/)
    assert.match(document.body.textContent, /chưa được cấp bộ lọc ngày/)
  } finally { await fixture.close() }
})

test('profile revocation aborts outdated reads and a late permissive response cannot restore custom data', async () => {
  const old = deferred(), queries = []
  let slow = false
  const fixture = await mount({ liveTourReports: (query, options) => {
    queries.push({ query, signal: options.signal })
    return slow && query.preset === 'custom' ? old.promise : Promise.resolve(page(capabilities(['today', 'custom']), 'VALID'))
  } }, operator(['today', 'custom']))
  try {
    slow = true
    await click('Tùy chỉnh')
    const oldRequest = queries.at(-1)
    assert.equal(oldRequest.query.preset, 'custom')
    await fixture.render(operator(['today']))
    assert.equal(oldRequest.signal.aborted, true)
    assert.equal(queries.at(-1).query.preset, 'today')
    await act(async () => old.resolve(page(capabilities(['today', 'custom']), 'LATE-PRIVATE')))
    assert.equal(button('Tùy chỉnh'), undefined)
    assert.doesNotMatch(document.body.textContent, /LATE-PRIVATE/)
  } finally { await fixture.close() }
})

test('report date revocation aborts pending board history and hides its data and exports', async () => {
  const old = deferred(); let historySignal
  const fixture = await mount({
    liveTourReports: async () => page(capabilities(['today'], ['yesterday'])),
    liveTourBoardHistory: (_query, options) => { historySignal = options.signal; return old.promise },
  }, operator(['today'], ['yesterday']))
  try {
    await click('Lịch sử Live Tour')
    await fixture.render(operator([], ['yesterday']))
    assert.equal(historySignal.aborted, true)
    await act(async () => old.resolve({ rows: [{ id: 'old', employee_name: 'OLD HISTORY' }], columns: [], capabilities: capabilities(['today'], ['yesterday']) }))
    assert.doesNotMatch(document.body.textContent, /OLD HISTORY/)
    assert.equal(button('Xuất excel'), undefined)
    assert.match(document.body.textContent, /chưa được cấp bộ lọc ngày/)
  } finally { await fixture.close() }
})

test('malformed server policy is fail closed and its accompanying rows never render', async () => {
  let reads = 0
  const fixture = await mount({ liveTourReports: async () => { reads++; return page({ ...capabilities(), date_filters: { version: 99, sections: { reports: all } } }, 'UNAUTHORIZED') } }, operator(['today']))
  try {
    assert.equal(reads, 1)
    assert.doesNotMatch(document.body.textContent, /UNAUTHORIZED/)
    assert.equal(button('Xuất excel'), undefined)
  } finally { await fixture.close() }
})

test('clearing a custom boundary suppresses reads and exports until the range is complete', async () => {
  const queries = []
  const fixture = await mount({ liveTourReports: async query => { queries.push(query); return page(capabilities(['custom'])) } }, operator(['custom']))
  try {
    const before = queries.length
    const from = [...document.querySelectorAll('.live-tour-filters-dates label')].find(label => label.textContent.startsWith('Từ ngày')).querySelector('input')
    await input(from, '')
    assert.equal(queries.length, before)
    assert.equal(button('Xuất excel'), undefined)
    assert.match(document.body.textContent, /Chọn đầy đủ khoảng ngày/)
    await input(from, '01-01-2026')
    assert.equal(queries.at(-1).preset, 'custom')
    assert.equal(queries.at(-1).date_from, '2026-01-01')
  } finally { await fixture.close() }
})

test('report-only board-history readers use report-month permission despite unrelated history-today grants', async () => {
  const queries = [], caps = capabilities(['month'], ['today'])
  const fixture = await mount({
    liveTourReports: async () => page(caps),
    liveTourBoardHistory: async query => { queries.push(query); return { rows: [], columns: [], capabilities: caps } },
  }, operator(['month'], ['today'], { live_tour_view: false, live_tour_history_view: false, live_tour_backup: false }))
  try {
    await click('Lịch sử Live Tour')
    assert.ok(queries.length)
    assert.equal(queries.at(-1).preset, 'month')
    assert.equal(button('Hôm nay'), undefined)
    assert.ok(button('Tháng này'))
  } finally { await fixture.close() }
})

test('history-view and backup-only accounts cannot enter standalone Reports or its board-history tab', async () => {
  for (const grant of ['live_tour_history_view', 'live_tour_backup']) {
    let reads = 0
    const fixture = await mount({
      liveTourReports: async () => { reads++; return page() },
      liveTourBoardHistory: async () => { reads++; return { rows: [], columns: [] } },
    }, operator(all, all, { live_tour_reports_view: false, live_tour_history_view: false, [grant]: true }))
    try {
      assert.equal(reads, 0)
      assert.equal(button('Lịch sử Live Tour'), undefined)
      assert.match(document.body.textContent, /chưa có quyền Xem báo cáo/)
    } finally { await fixture.close() }
  }
})

test('pending Excel exports abort on date-policy revocation and authenticated account changes', async () => {
  for (const change of ['policy', 'account']) {
    const exports = []
    const fixture = await mount({
      liveTourReports: async () => page(capabilities(['today'])),
      exportLiveTourExcel: (kind, filters, options) => { const task = deferred(); exports.push({ ...task, kind, filters, signal: options.signal }); return task.promise },
    }, operator(['today']))
    try {
      await click('Xuất excel')
      assert.equal(exports[0].filters.preset, 'today')
      assert.equal(exports[0].signal.aborted, false)
      await fixture.render(change === 'policy' ? operator([]) : { ...operator(['today']), id: 'other' })
      assert.equal(exports[0].signal.aborted, true)
      await act(async () => exports[0].reject(new Error('obsolete export error')))
      assert.equal(document.querySelector('[role="alert"]'), null)
    } finally { await fixture.close() }
  }
})

test('a 403 carrying fresh date capabilities selects an authorized fallback and discards forbidden rows', async () => {
  let revoked = false
  const queries = []
  const fixture = await mount({ liveTourReports: async query => {
    queries.push(query)
    if (revoked && query.preset === 'month') {
      const error = new Error('Date permission revoked')
      error.status = 403
      error.payload = { detail: { capabilities: capabilities(['today']) } }
      throw error
    }
    return page(capabilities(revoked ? ['today'] : ['today', 'month']), revoked ? 'AFTER-REVOCATION' : 'OLD')
  } }, operator(['today', 'month']))
  try {
    await click('Tháng này')
    await act(async () => document.querySelector('[aria-label="Sửa báo cáo hóa đơn"]').click())
    assert.ok(document.querySelector('[role="dialog"]'))
    revoked = true
    await click('Làm mới')
    assert.equal(queries.at(-1).preset, 'today')
    assert.equal(button('Tháng này'), undefined)
    assert.equal(document.querySelector('[role="dialog"]'), null)
    assert.match(document.body.textContent, /BILL-AFTER-REVOCATION/)
    assert.doesNotMatch(document.body.textContent, /BILL-OLD/)
  } finally { await fixture.close() }
})

test('a date policy change invalidates the legacy full snapshot before re-reading modern permissions', async () => {
  const queries = []
  const firstPage = page({ export: true, reports_edit: true }, 'LEGACY-PRIVATE')
  const legacy = { revision: 7, reports: firstPage.rows, invoices: firstPage.invoices, pending: [], performance: [], capabilities: firstPage.capabilities, payment_settings: {} }
  const fixture = await mount({ liveTourReports: async query => {
    queries.push(query)
    return queries.length === 1 ? legacy : page(capabilities(['today']), 'MODERN')
  } }, operator(['all', 'today'], all))
  try {
    assert.match(document.body.textContent, /BILL-LEGACY-PRIVATE/)
    await fixture.render(operator(['today']))
    assert.ok(queries.length > 1)
    assert.equal(queries.at(-1).preset, 'today')
    assert.match(document.body.textContent, /BILL-MODERN/)
    assert.doesNotMatch(document.body.textContent, /LEGACY-PRIVATE/)
  } finally { await fixture.close() }
})

test('partial custom date drafts preserve editable text and block stale reads, exports and PDF/PNG across other filter edits', async () => {
  const reads = [], files = [], exports = []
  const fixture = await mount({
    liveTourReports: async query => { reads.push(query); return page(capabilities(['custom'])) },
    readCustomerCountPdf: (_filters, options) => { const task = deferred(); files.push({ ...task, signal: options.signal }); return task.promise },
    readCustomerCountPng: (_filters, options) => { const task = deferred(); files.push({ ...task, signal: options.signal }); return task.promise },
    exportLiveTourExcel: (_kind, _filters, options) => { const task = deferred(); exports.push({ ...task, signal: options.signal }); return task.promise },
  }, operator(['custom']))
  try {
    await click('Xuất excel')
    await click('Chia sẻ số khách · PDF/PNG')
    assert.equal(files.length, 2)
    const before = reads.length
    const from = [...document.querySelectorAll('.live-tour-filters-dates label')].find(label => label.textContent.startsWith('Từ ngày')).querySelector('input[type="text"]')
    await input(from, '12-0')
    assert.equal(from.value, '12-0', 'partial input must remain mounted for the user to finish')
    assert.equal(reads.length, before)
    assert.equal(Boolean(button('Xuất excel')), false)
    assert.equal(Boolean(button('Chia sẻ số khách · PDF/PNG')), false)
    assert.equal(button('Làm mới').disabled, true)
    assert.equal(document.querySelector('[role="dialog"]'), null)
    assert.ok(files.every(file => file.signal.aborted))
    assert.ok(exports.every(file => file.signal.aborted))
    await input(document.querySelector('input[placeholder="Tìm tên nhân viên"]'), 'Changed during draft')
    assert.equal(reads.length, before, 'other filter edits must not submit the previous saved date')
    assert.equal(from.value, '12-0')
    await input(from, '01-01-2026')
    assert.equal(reads.at(-1).date_from, '2026-01-01')
    assert.equal(reads.at(-1).employee, 'Changed during draft')
    assert.ok(reads.length > before)
    assert.ok(button('Xuất excel'))
    assert.equal(document.querySelector('[role="dialog"]'), null, 'finishing the date must not revive old prepared files')
  } finally { await fixture.close() }
})

test('partial end-date and single-date drafts cannot silently reuse committed values', async () => {
  for (const fieldName of ['Đến ngày', 'Lọc ngày hóa đơn']) {
    let reads = 0
    const fixture = await mount({ liveTourReports: async () => { reads++; return page(capabilities(['custom'])) } }, operator(['custom']))
    try {
      const field = fieldName === 'Lọc ngày hóa đơn' ? document.querySelector('input[aria-label="Lọc ngày hóa đơn"]')
        : [...document.querySelectorAll('.live-tour-filters-dates label')].find(label => label.textContent.startsWith(fieldName)).querySelector('input[type="text"]')
      const before = reads
      await input(field, '31-0')
      await input(document.querySelector('input[placeholder="Tìm tên nhân viên"]'), 'New employee')
      assert.equal(reads, before)
      assert.equal(Boolean(button('Xuất excel')), false)
      assert.equal(field.value, '31-0')
    } finally { await fixture.close() }
  }
})
