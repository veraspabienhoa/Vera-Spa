import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { defaultTourYesterdayFilters } from '../src/lib/liveTourFilters.js'
import { EMPTY_REPORT_PAGE, reportReadQuery, validateReportPage } from '../src/lib/liveTourReportPage.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LiveTourReportsPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'report-api-fixture', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__reportPagingApi;', loader: 'js' }))
  } }],
})
const queryDate = defaultTourYesterdayFilters().date_from
const capabilities = { export: true, paid_invoice_view: true, reports_edit: true, reports_delete: true, invoice_view: true, pending_view: true }
const reportRow = (id, patch = {}) => ({ id, invoice_id: `invoice-${id}`, bill_no: `BILL-${id}`, employee_name: 'An',
  business_date: queryDate, effective_at: `${queryDate}T09:00:00+07:00`, service: 'Body', total: 100, tip: 10, ...patch })
function reportPage(patch = {}) {
  const rows = patch.rows || [reportRow('one')]
  return { ...EMPTY_REPORT_PAGE, revision: 7, total: rows.length, rows,
    invoices: rows.map(row => ({ ...row, id: row.invoice_id, entries: [{ employee_name: row.employee_name, service: row.service, price: row.total }] })),
    capabilities, ...patch, summary: { ...EMPTY_REPORT_PAGE.summary, ...patch.summary } }
}
function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}
async function mount(api, user = { role: 'admin', employee_username: 'operator' }) {
  globalThis.__reportPagingApi = api
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(document.querySelector('#root'))
  await act(async () => root.render(React.createElement(module.exports.default, { user })))
  return { root, Component: module.exports.default, close: () => act(() => root.unmount()) }
}
async function click(label, selector = 'button') {
  const button = [...document.querySelectorAll(selector)].find(node => node.textContent === label)
  assert.ok(button, `Missing button ${label}`)
  await act(async () => button.click())
}
async function type(placeholder, value) {
  const field = document.querySelector(`input[placeholder="${placeholder}"]`)
  assert.ok(field, `Missing input ${placeholder}`)
  await act(async () => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(field, value)
    field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
}
const money = value => `${Number(value).toLocaleString('vi-VN')} đ`

test('report read contract applies money to the selected tab and preserves ISO date/zero', () => {
  const filters = { preset: 'custom', date: '2026-10-09', date_from: '2026-10-09', date_to: '2026-10-09',
    employee: 'Ánh', service: 'Body', total_amount: 0, tip_amount: '50' }
  assert.deepEqual(reportReadQuery(filters, 'revenue', 'early', 4), { tab: 'revenue', page: 4, page_size: 100, preset: 'custom',
    date: '2026-10-09', date_from: '2026-10-09', date_to: '2026-10-09', employee: 'Ánh', service: 'Body', total_amount: 0 })
  assert.equal(reportReadQuery(filters, 'tip', 'all').tip_amount, '50')
  assert.equal(reportReadQuery(filters, 'performance', 'early').performance_timing, 'early')
  assert.equal(reportReadQuery(filters, 'employee', 'all').total_amount, undefined)
  assert.equal(reportReadQuery(filters, 'employee', 'all').tip_amount, undefined)
})

test('unbounded and incomplete legacy responses fail closed rather than yielding page-local totals', () => {
  assert.throws(() => validateReportPage({ reports: Array(5000).fill({}) }), /phân trang/)
  assert.throws(() => validateReportPage(reportPage({ rows: Array(101).fill(reportRow('too-many')) })), /phân trang/)
  assert.throws(() => validateReportPage(reportPage({ summary: { totalRevenue: NaN } })), /phân trang/)
  assert.equal(validateReportPage(reportPage({ total: 1000000, pages: 10000 })).total, 1000000)
})

test('million-row history renders only the requested page with exact filter-wide totals and ISO queries', async () => {
  const requests = []
  const fullSummary = { totalRevenue: 789654321, serviceRevenue: 777000000, tip: 12654321,
    invoiceCount: 600001, zeroInvoices: 17, discount: 1234500, pendingInvoiceCount: 38 }
  const fixture = await mount({ liveTourReports: async (query, options) => {
    requests.push({ query, options })
    return reportPage({ page: query.page, total: 1000000, pages: 10000, summary: fullSummary,
      rows: Array.from({ length: 100 }, (_, i) => reportRow(`${query.page}-${i}`)) })
  } })
  try {
    assert.equal(requests.length, 1)
    assert.deepEqual(requests[0].query, { tab: 'revenue', page: 1, page_size: 100, preset: 'yesterday', date_from: queryDate, date_to: queryDate })
    assert.ok(requests[0].options.signal instanceof AbortSignal)
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 100)
    assert.match(document.querySelector('.tour-revenue-summary').textContent, new RegExp(money(fullSummary.totalRevenue)))
    assert.match(document.querySelector('.live-tour-report-extra-metrics').textContent, /38.*17/)
    assert.match(document.querySelector('.live-tour-report-extra-metrics').textContent, new RegExp(money(fullSummary.discount)))
    assert.match(document.querySelector('.table-pager').textContent, /1–100 \/ 1\.000\.000 dòng/)
    const [year, month, day] = queryDate.split('-')
    assert.match(document.querySelector('.live-tour-report-table tbody').textContent, new RegExp(`${day}-${month}-${year}`))
    await click('Trang sau')
    assert.equal(requests.length, 2)
    assert.equal(requests[1].query.page, 2)
    assert.match(document.querySelector('.table-pager').textContent, /101–200/)
    assert.match(document.querySelector('.live-tour-report-table tbody').textContent, /BILL-2-0/)
    assert.doesNotMatch(document.querySelector('.live-tour-report-table tbody').textContent, /BILL-1-0/)
    assert.match(document.querySelector('.tour-revenue-summary').textContent, new RegExp(money(fullSummary.totalRevenue)))
    await type('Tìm tên nhân viên', 'Nguyễn')
    assert.equal(requests.at(-1).query.page, 1, 'new filters reset before issuing a request')
    assert.equal(requests.at(-1).query.employee, 'Nguyễn')
  } finally { await fixture.close() }
})

test('rapid filters abort old reads and ignore late success, failure and unmounted responses', async () => {
  const pending = []
  const fixture = await mount({ liveTourReports: (query, options) => {
    if (!query.employee) return Promise.resolve(reportPage())
    const work = deferred(); pending.push({ ...work, query, signal: options.signal }); return work.promise
  } })
  try {
    await type('Tìm tên nhân viên', 'Old')
    await type('Tìm tên nhân viên', 'Newest')
    assert.equal(pending.length, 2)
    assert.equal(pending[0].signal.aborted, true)
    assert.equal(pending[1].signal.aborted, false)
    await act(async () => pending[1].resolve(reportPage({ rows: [reportRow('CURRENT')], summary: { totalRevenue: 987654 } })))
    await act(async () => pending[0].resolve(reportPage({ rows: [reportRow('STALE')], summary: { totalRevenue: 123456 } })))
    assert.match(document.body.textContent, /BILL-CURRENT/)
    assert.doesNotMatch(document.body.textContent, /BILL-STALE/)
    assert.match(document.querySelector('.tour-revenue-summary').textContent, /987\.654 đ/)
    await type('Tìm tên nhân viên', 'Failure')
    await type('Tìm tên nhân viên', 'After failure')
    await act(async () => pending[2].reject(new Error('obsolete network error')))
    await act(async () => pending[3].resolve(reportPage({ rows: [reportRow('LATEST')] })))
    assert.equal(document.querySelector('[role="alert"]'), null)
    assert.match(document.body.textContent, /BILL-LATEST/)
    await type('Tìm tên nhân viên', 'Unmount')
    await fixture.close()
    assert.equal(pending[4].signal.aborted, true)
    await act(async () => pending[4].resolve(reportPage()))
    assert.equal(document.querySelector('#root').textContent, '')
  } finally { if (document.querySelector('#root').hasChildNodes()) await fixture.close() }
})

test('exports keep all applied filters across tabs without pagination or hidden money filters', async () => {
  const exports = [], requests = []
  const fixture = await mount({
    liveTourReports: async query => { requests.push(query); return reportPage({ page: query.page, total: 500, pages: 5 }) },
    exportLiveTourExcel: async (kind, query) => { exports.push({ kind, query }) },
  })
  try {
    await type('Nhập hoặc chọn số hóa đơn', 'INV')
    await type('Tìm tên nhân viên', 'Ánh')
    await type('Tìm tên hoặc số điện thoại', 'Khách 090')
    await type('Tìm dịch vụ', 'Body')
    await type('Tất cả số tiền', '0')
    await click('Trang sau')
    await click('Xuất excel')
    assert.equal(exports[0].kind, 'reports')
    assert.equal(exports[0].query.total_amount, 0)
    for (const [key, value] of Object.entries({ bill_no: 'INV', employee: 'Ánh', customer: 'Khách 090', service: 'Body', date_from: queryDate, date_to: queryDate })) {
      assert.equal(exports[0].query[key], value)
    }
    assert.equal(exports[0].query.page, undefined)
    assert.equal(exports[0].query.page_size, undefined)
    assert.equal(requests.at(-1).page, 2)
    await click('Tiền Tip')
    await type('Tất cả số tiền', '50')
    await click('Xuất excel')
    assert.equal(exports[1].kind, 'tip')
    assert.equal(exports[1].query.tip_amount, 50)
    assert.equal(exports[1].query.total_amount, '')
    await click('Combo')
    await click('Xuất excel')
    assert.equal(exports[2].query.report_kind, 'combos')
    assert.equal(exports[2].query.tip_amount, '')
    await click('Thời gian dịch vụ')
    await click('Trễ')
    await click('Xuất excel')
    assert.equal(requests.at(-1).tab, 'performance')
    assert.equal(requests.at(-1).performance_timing, 'late')
    assert.equal(exports[3].kind, 'performance')
    assert.equal(exports[3].query.performance_timing, 'late')
  } finally { await fixture.close() }
})

test('employee and TIP metrics use complete server aggregates rather than the single visible report row', async () => {
  const fixture = await mount({ liveTourReports: async () => reportPage({ total: 700, pages: 7,
    summary: { tip: 543210, tipEmployeeCount: 123 }, employee_totals: [
      { employee: 'Aggregate one', service: 1000, tip: 20, total: 1020, tourRows: 200, requestRows: 50, rows: 250 },
      { employee: 'Off-page employee', service: 9000, tip: 30, total: 9030, tourRows: 400, requestRows: 50, rows: 450 },
    ],
  }) })
  try {
    await click('Theo nhân viên')
    assert.match(document.querySelector('.employee-revenue-table').textContent, /Off-page employee/)
    assert.match(document.querySelector('.employee-revenue-kpis').textContent, /10\.000 đ/)
    assert.match(document.querySelector('.employee-revenue-table').textContent, /450/)
    await click('Tiền Tip')
    assert.match(document.querySelector('.live-tour-report-metrics').textContent, /123.*543\.210 đ/)
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 1)
  } finally { await fixture.close() }
})

test('page shrink reloads the last valid page without presenting blank results as final', async () => {
  let shrunk = false
  const requests = []
  const fixture = await mount({ liveTourReports: async query => {
    requests.push(query.page)
    return reportPage({ page: query.page, total: shrunk ? 1 : 101, pages: shrunk ? 1 : 2,
      rows: shrunk && query.page === 2 ? [] : [reportRow(`${query.page}`)] })
  } })
  try {
    await click('Trang sau')
    shrunk = true
    await click('Làm mới')
    assert.deepEqual(requests, [1, 2, 2, 1])
    assert.match(document.querySelector('.table-pager').textContent, /Trang 1 \/ 1/)
    assert.match(document.querySelector('.live-tour-report-table tbody').textContent, /BILL-1/)
  } finally { await fixture.close() }
})

test('leaving a pending history request aborts it and cannot block report actions', async () => {
  const history = deferred(); let historySignal
  const fixture = await mount({
    liveTourReports: async () => reportPage(),
    liveTourBoardHistory: (_query, options) => { historySignal = options.signal; return history.promise },
  })
  try {
    await click('Lịch sử Live Tour')
    assert.equal(historySignal.aborted, false)
    await click('Doanh thu')
    assert.equal(historySignal.aborted, true)
    await act(async () => history.resolve({ rows: [{ id: 'old-history', employee_name: 'OLD HISTORY' }], columns: [] }))
    assert.equal(document.querySelector('button[aria-label="Sửa báo cáo hóa đơn"]').disabled, false)
    assert.doesNotMatch(document.body.textContent, /OLD HISTORY/)
    assert.doesNotMatch(document.body.textContent, /Đang cập nhật báo cáo/)
  } finally { await fixture.close() }
})

test('view permission gates reads and non-admin UI omits privileged tabs and mutation/export controls', async () => {
  let reads = 0
  const api = { liveTourReports: async () => { reads++; return reportPage({ invoices: [], capabilities: {} }) } }
  const denied = await mount(api, { role: 'letan', permissions: {} })
  assert.equal(reads, 0)
  await denied.close()
  const allowed = await mount(api, { role: 'letan', permissions: { live_tour_reports_view: true } })
  try {
    assert.equal(reads, 1)
    assert.equal(document.querySelector('button[aria-label="Sửa báo cáo hóa đơn"]'), null)
    assert.equal(document.querySelector('button[aria-label="Xem hóa đơn"]'), null)
    assert.ok(![...document.querySelectorAll('[role="tab"]')].some(node => /Tiền Tip|Thời gian dịch vụ/.test(node.textContent)))
    assert.ok(![...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'))
  } finally { await allowed.close() }
})

test('immediate history navigation gets export grants without waiting for any report payload', async () => {
  const report = deferred(); let reportSignal, exports = 0
  const fixture = await mount({
    liveTourReports: (_query, options) => { reportSignal = options.signal; return report.promise },
    liveTourBoardHistory: async () => ({ rows: [], columns: [], capabilities: { export: true } }),
    exportLiveTourBoardHistory: async () => { exports++ },
  })
  try {
    await click('Lịch sử Live Tour')
    assert.equal(reportSignal.aborted, true)
    await click('Xuất excel')
    assert.equal(exports, 1)
    await act(async () => report.resolve(reportPage({ capabilities: { export: false } })))
    await click('Xuất excel')
    assert.equal(exports, 2, 'late report capabilities cannot replace history authority')
  } finally { await fixture.close() }
})

test('history from a previous identity is hidden while the new scoped read is pending', async () => {
  const newer = deferred(); let reads = 0
  const fixture = await mount({
    liveTourReports: async () => reportPage(),
    liveTourBoardHistory: () => ++reads === 1 ? Promise.resolve({ rows: [{ id: 'private', employee_name: 'OLD PRIVATE ROW' }], columns: [], capabilities: { export: true } }) : newer.promise,
  })
  try {
    await click('Lịch sử Live Tour')
    assert.match(document.body.textContent, /OLD PRIVATE ROW/)
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: {
      role: 'letan', employee_username: 'new-operator', permissions: { live_tour_reports_view: true },
    } })))
    assert.doesNotMatch(document.body.textContent, /OLD PRIVATE ROW/)
    assert.ok(![...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'))
    await act(async () => newer.resolve({ rows: [], columns: [], capabilities: {} }))
  } finally { await fixture.close() }
})

test('an open invoice dialog cannot survive a change of authenticated identity', async () => {
  const fixture = await mount({ liveTourReports: async () => reportPage() })
  try {
    await act(async () => document.querySelector('button[aria-label="Sửa báo cáo hóa đơn"]').click())
    assert.ok(document.querySelector('[role="dialog"]'))
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: {
      role: 'letan', employee_username: 'different-operator', permissions: { live_tour_reports_view: true },
    } })))
    assert.equal(document.querySelector('[role="dialog"]'), null)
  } finally { await fixture.close() }
})

test('a committed edit refreshes the current filters and keeps its original expected revision', async () => {
  const mutation = deferred(), requests = [], writes = []
  const fixture = await mount({
    liveTourReports: async query => { requests.push(query); return reportPage() },
    liveTourAction: body => { writes.push(body); return mutation.promise },
  })
  try {
    await act(async () => document.querySelector('button[aria-label="Sửa báo cáo hóa đơn"]').click())
    await act(async () => document.querySelector('[role="dialog"] button[type="submit"]').click())
    assert.equal(writes[0].expected_revision, 7)
    assert.equal(writes[0].response_view, 'receipt')
    await type('Tìm tên nhân viên', 'After edit')
    await act(async () => mutation.resolve({ ok: true, revision: 8, result: { invoice: reportRow('one') } }))
    assert.deepEqual(requests.map(query => query.employee || ''), ['', 'After edit', 'After edit'])
    assert.equal(document.querySelector('[role="dialog"]'), null)
  } finally { await fixture.close() }
})

test('PDF/PNG dialogs are account/permission scoped, abort late reads and revoke both prepared files', async () => {
  const requests = [], created = [], revoked = []
  const originalCreate = URL.createObjectURL, originalRevoke = URL.revokeObjectURL
  URL.createObjectURL = file => { const url = `blob:report-${created.length}`; created.push({ url, file }); return url }
  URL.revokeObjectURL = url => revoked.push(url)
  const firstUser = { id: 'user-one', role: 'admin', employee_username: 'operator', permissions: {} }
  const nextUser = { ...firstUser, id: 'user-two' }
  const prepare = (format, filters, options) => { const read = deferred(); requests.push({ ...read, format, filters, signal: options.signal }); return read.promise }
  const fixture = await mount({
    liveTourReports: async () => reportPage(),
    readCustomerCountPdf: (...args) => prepare('pdf', ...args),
    readCustomerCountPng: (...args) => prepare('png', ...args),
  }, firstUser)
  try {
    await click('Chia sẻ số khách · PDF/PNG')
    assert.equal(requests.length, 2)
    for (const read of requests) { assert.equal(read.filters.date_from, queryDate); assert.equal(read.filters.page, undefined) }
    assert.match(document.querySelector('[role="dialog"]').textContent, /Đang tạo PDF.*Đang tạo PNG/)
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: nextUser })))
    assert.ok(requests.every(read => read.signal.aborted))
    assert.equal(document.querySelector('[role="dialog"]'), null)
    await act(async () => {
      for (const read of requests) read.resolve(new Blob(['old private report'], { type: read.format === 'pdf' ? 'application/pdf' : 'image/png' }))
    })
    assert.equal(created.length, 0, 'late responses cannot create files for the previous account')
    await click('Chia sẻ số khách · PDF/PNG')
    await act(async () => {
      for (const read of requests.slice(2)) read.resolve(new Blob(['current report'], { type: read.format === 'pdf' ? 'application/pdf' : 'image/png' }))
    })
    assert.match(document.querySelector('[role="dialog"]').textContent, /PDF đã sẵn sàng.*PNG đã sẵn sàng/)
    assert.equal(created.length, 2)
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: { ...nextUser, permissions: { live_tour_export: false } } })))
    assert.equal(document.querySelector('[role="dialog"]'), null)
    assert.deepEqual(revoked, ['blob:report-0', 'blob:report-1'])
    assert.ok(requests.slice(2).every(read => read.signal.aborted))
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: nextUser })))
    assert.equal(document.querySelector('[role="dialog"]'), null, 'restoring an identity cannot reopen its old report')
    assert.equal(requests.length, 4)
  } finally {
    await fixture.close()
    URL.createObjectURL = originalCreate; URL.revokeObjectURL = originalRevoke
  }
})

function legacyPage(patch = {}) {
  const page = reportPage(patch)
  return { revision: page.revision, invoices: page.invoices, reports: page.rows, pending: [], performance: [],
    capabilities: page.capabilities, payment_settings: page.payment_settings, ...patch }
}

test('new UI on the old backend pages, filters and exports locally until a refresh adopts bounded reads', async () => {
  const requests = [], exports = []
  const old = legacyPage({ reports: Array.from({ length: 201 }, (_, i) => reportRow(`legacy-${i}`, { employee_name: i === 200 ? 'Bình' : 'An' })) })
  old.invoices = old.reports.map(row => ({ ...row, id: row.invoice_id, entries: [{ employee_name: row.employee_name, service: row.service, price: 90 }] }))
  const fixture = await mount({
    liveTourReports: async query => { requests.push(query); return requests.length === 1 ? old : reportPage({ rows: [reportRow('NEW SERVER')] }) },
    exportLiveTourExcel: async (kind, query) => exports.push({ kind, query }),
  })
  try {
    assert.equal(document.querySelector('.live-tour-reports-page').dataset.reportReadMode, 'legacy')
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 100)
    assert.match(document.querySelector('.tour-revenue-summary').textContent, /20\.100 đ/)
    await click('Trang sau')
    assert.match(document.querySelector('.live-tour-report-table tbody').textContent, /BILL-legacy-100/)
    assert.equal(requests.length, 1, 'old response must not cause another full-history fetch for a page')
    await type('Tìm tên nhân viên', 'Bình')
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 1)
    assert.match(document.querySelector('.table-pager').textContent, /Trang 1 \/ 1/)
    assert.match(document.querySelector('.tour-revenue-summary').textContent, /100 đ/)
    await click('Xuất excel')
    assert.equal(exports[0].query.employee, 'Bình')
    assert.equal(exports[0].query.page, undefined)
    const date = document.querySelector('input[aria-label="Lọc ngày hóa đơn"]')
    await act(async () => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(date, '01-01-2020')
      date.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    })
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 0)
    await click('Xuất excel')
    assert.equal(exports[1].query.date, '2020-01-01')
    assert.equal(exports[1].query.date_from, '2020-01-01')
    assert.equal(requests.length, 1)
    await click('Tiền Tip')
    assert.equal(requests.length, 1, 'legacy tabs reuse the authorized snapshot')
    await click('Làm mới')
    assert.equal(requests.length, 2)
    assert.equal(document.querySelector('.live-tour-reports-page').dataset.reportReadMode, 'paged')
    await click('Doanh thu')
    assert.equal(requests.length, 3, 'once upgraded, new queries must use bounded server reads')
  } finally { await fixture.close() }
})

for (const [label, user, allowedExport] of [
  ['admin', { role: 'admin', employee_username: 'admin' }, true],
  ['explicit export', { role: 'letan', employee_username: 'allowed', permissions: { live_tour_reports_view: true, live_tour_export: true } }, true],
  ['no export', { role: 'letan', employee_username: 'restricted', permissions: { live_tour_reports_view: true } }, false],
]) test(`old history immediate navigation: ${label} uses only verified shell export authority`, async () => {
  const oldRead = deferred(); let signal, reads = 0
  const fixture = await mount({
    liveTourReports: (_query, options) => { reads++; signal = options.signal; return oldRead.promise },
    liveTourBoardHistory: async () => ({ ok: true, rows: [], columns: [], count: 0 }),
  }, user)
  try {
    await click('Lịch sử Live Tour')
    assert.equal(signal.aborted, true)
    assert.equal(reads, 1, 'no extra all-history request is needed for history grants')
    assert.equal([...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'), allowedExport)
    await act(async () => oldRead.resolve(legacyPage()))
    assert.equal([...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'), allowedExport)
  } finally { await fixture.close() }
})

test('old history retains explicit report export denial instead of widening from shell fallback', async () => {
  const fixture = await mount({
    liveTourReports: async () => legacyPage({ capabilities: { export: false } }),
    liveTourBoardHistory: async () => ({ ok: true, rows: [], columns: [], count: 0 }),
  }, { role: 'letan', permissions: { live_tour_reports_view: true, live_tour_export: true } })
  try {
    await click('Lịch sử Live Tour')
    assert.ok(![...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'))
  } finally { await fixture.close() }
})

test('a failed post-commit reload discards the legacy snapshot; a new filter retries the server', async () => {
  const writes = [], reads = []
  const fixture = await mount({
    liveTourReports: async query => {
      reads.push(query)
      if (reads.length === 1) return legacyPage()
      if (reads.length === 2) throw new Error('failed refresh after commit')
      return legacyPage({ reports: [reportRow('AFTER COMMIT')] })
    },
    liveTourAction: async body => { writes.push(body); return { ok: true, revision: 8 } },
  })
  try {
    await act(async () => document.querySelector('button[aria-label="Sửa báo cáo hóa đơn"]').click())
    await act(async () => document.querySelector('[role="dialog"] button[type="submit"]').click())
    assert.equal(writes[0].expected_revision, 7)
    assert.equal(reads.length, 2)
    assert.match(document.querySelector('[role="alert"]').textContent, /Đã lưu điều chỉnh/)
    assert.doesNotMatch(document.body.textContent, /BILL-one/)
    await type('Tìm tên nhân viên', 'An')
    assert.equal(reads.length, 3, 'must fetch rather than revive the pre-edit snapshot')
    assert.match(document.body.textContent, /BILL-AFTER COMMIT/)
    assert.doesNotMatch(document.body.textContent, /BILL-one/)
  } finally { await fixture.close() }
})

test('legacy snapshots are discarded when the authenticated account changes', async () => {
  let reads = 0
  const fixture = await mount({ liveTourReports: async () => legacyPage({ reports: [reportRow(++reads === 1 ? 'OLD IDENTITY' : 'NEW IDENTITY')] }) }, { id: 'first', role: 'admin' })
  try {
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: { id: 'second', role: 'admin' } })))
    assert.equal(reads, 2)
    assert.doesNotMatch(document.body.textContent, /BILL-OLD IDENTITY/)
    assert.match(document.body.textContent, /BILL-NEW IDENTITY/)
  } finally { await fixture.close() }
})

test('HTTP failures never activate legacy compatibility or trigger a fallback request', async () => {
  let reads = 0
  const fixture = await mount({ liveTourReports: async () => { reads++; throw new Error('HTTP 503') } })
  try {
    assert.equal(reads, 1)
    assert.match(document.querySelector('[role="alert"]').textContent, /HTTP 503/)
    assert.notEqual(document.querySelector('.live-tour-reports-page').dataset.reportReadMode, 'legacy')
    assert.equal(document.querySelectorAll('.live-tour-report-table tbody tr').length, 0)
  } finally { await fixture.close() }
})

test('legacy permission changes recheck the server instead of keeping previous cached grants', async () => {
  let reads = 0
  const user = { id: 'operator', role: 'letan', permissions: { live_tour_reports_view: true, live_tour_export: true } }
  const fixture = await mount({ liveTourReports: async () => legacyPage({ capabilities: { export: ++reads === 1 } }) }, user)
  try {
    assert.ok([...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'))
    await act(async () => fixture.root.render(React.createElement(fixture.Component, { user: {
      ...user, permissions: { live_tour_reports_view: true, live_tour_export: false },
    } })))
    assert.equal(reads, 2)
    assert.ok(![...document.querySelectorAll('button')].some(node => node.textContent === 'Xuất excel'))
  } finally { await fixture.close() }
})

test('commit invalidates a legacy snapshot even if the operator switched to history during the write', async () => {
  const saved = deferred(); let reads = 0
  const fixture = await mount({
    liveTourReports: async () => { reads++; return reads === 1 ? legacyPage() : legacyPage({ reports: [] }) },
    liveTourBoardHistory: async () => ({ rows: [], columns: [], capabilities: { export: true } }),
    liveTourAction: () => saved.promise,
  })
  try {
    await act(async () => document.querySelector('button[aria-label="Sửa báo cáo hóa đơn"]').click())
    await act(async () => document.querySelector('[role="dialog"] button[type="submit"]').click())
    await click('Lịch sử Live Tour')
    await act(async () => saved.resolve({ ok: true, revision: 8 }))
    await click('Doanh thu')
    assert.equal(reads, 2)
    assert.doesNotMatch(document.body.textContent, /BILL-one/)
  } finally { await fixture.close() }
})
