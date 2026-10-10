import assert from 'node:assert/strict'
import test from 'node:test'
import vm from 'node:vm'
import { build } from 'esbuild'

// Exercise the real API wrapper and shared-read cancellation, not a mocked page API.
const built = await build({
  stdin: { contents: "export { veraApi } from './src/lib/api';", resolveDir: process.cwd() },
  bundle: true, write: false, platform: 'node', format: 'cjs',
  define: { 'import.meta.env': '{"VITE_VERA_API_BASE_URL":"https://api.example.test"}' },
  plugins: [{ name: 'auth-fixture', setup(b) {
    b.onResolve({ filter: /(^|\/)supabase$/ }, () => ({ path: 'auth', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const getCurrentSession = async () => null; export const refreshCurrentSession = async () => null; export const isSupabaseConfigured = false; export const supabase = null;' }))
  } }],
})
function apiFixture(fetch) {
  const downloads = []
  const context = vm.createContext({
    module: { exports: {} }, fetch, Headers, AbortController, AbortSignal, URL, URLSearchParams, structuredClone,
    setTimeout, clearTimeout,
    document: { createElement: () => { const anchor = { click() { downloads.push({ href: this.href, filename: this.download }) }, remove() {} }; return anchor }, body: { appendChild() {} } },
    window: { setTimeout: callback => { callback(); return 0 } },
  })
  context.exports = context.module.exports
  vm.runInContext(built.outputFiles[0].text, context)
  return { api: context.module.exports.veraApi, downloads }
}

test('report HTTP requests carry bounded page/all filters, preserve zero and propagate abort without retry', async () => {
  const requests = []
  const { api } = apiFixture((url, options) => {
    requests.push({ url: new URL(url), options })
    return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true }))
  })
  const controller = new AbortController()
  const read = api.liveTourReports({ tab: 'revenue', page: 5, page_size: 100, date_from: '2026-10-09', date_to: '2026-10-09',
    date: '2026-10-09', employee: 'Ánh', service: 'Body', customer: 'Khách 090', bill_no: 'BILL', total_amount: 0, preset: undefined, tip_amount: '' }, { signal: controller.signal })
  await new Promise(setImmediate)
  assert.equal(requests.length, 1)
  assert.equal(requests[0].url.pathname, '/v2/live-tour/reports')
  const expected = { tab: 'revenue', page: '5', page_size: '100', date_from: '2026-10-09', date_to: '2026-10-09',
    date: '2026-10-09', employee: 'Ánh', service: 'Body', customer: 'Khách 090', bill_no: 'BILL', total_amount: '0' }
  assert.deepEqual(Object.fromEntries(requests[0].url.searchParams), expected)
  controller.abort()
  await assert.rejects(read, error => error.name === 'AbortError')
  assert.equal(requests[0].options.signal.aborted, true)
  assert.equal(requests.length, 1, 'aborted reads must not retry')
})

test('Excel transport exports the whole filter, never the viewed page, including zero-money and timing', async () => {
  const requests = []
  const { api, downloads } = apiFixture(async (url, options) => {
    requests.push({ url: new URL(url), options })
    return new Response('fixture-workbook', { status: 200, headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } })
  })
  await api.exportLiveTourExcel('reports', { page: 9, page_size: 100, date: '2026-10-09', date_from: '2026-10-09', date_to: '2026-10-09',
    employee: 'Ánh', service: 'Body', bill_no: 'BILL', total_amount: 0, report_kind: 'combos' })
  assert.deepEqual(Object.fromEntries(requests[0].url.searchParams), { kind: 'reports', bill_no: 'BILL', employee: 'Ánh', service: 'Body',
    report_kind: 'combos', total_amount: '0', date_from: '2026-10-09', date_to: '2026-10-09', date: '2026-10-09' })
  await api.exportLiveTourExcel('performance', { performance_timing: 'early', page: 8, page_size: 100 })
  assert.deepEqual(Object.fromEntries(requests[1].url.searchParams), { kind: 'performance', performance_timing: 'early' })
  assert.equal(downloads.length, 2)
  assert.equal(downloads[0].filename, 'VeraSpa_LiveTour_reports.xlsx')
})

test('history transport also cancels obsolete reads while preserving its supported date/employee scope', async () => {
  let request
  const { api } = apiFixture((url, options) => {
    request = { url: new URL(url), options }
    return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true }))
  })
  const controller = new AbortController()
  const read = api.liveTourBoardHistory({ date_from: '2026-10-01', date_to: '2026-10-09', employee: ' Ánh ', customer: 'unsupported' }, { signal: controller.signal })
  await new Promise(setImmediate)
  assert.deepEqual(Object.fromEntries(request.url.searchParams), { date_from: '2026-10-01', date_to: '2026-10-09', employee: 'Ánh' })
  controller.abort()
  await assert.rejects(read, error => error.name === 'AbortError')
  assert.equal(request.options.signal.aborted, true)
})

test('all protected read and export transports preserve the selected preset', async () => {
  const requests = []
  const { api } = apiFixture(async (url, options) => {
    const parsed = new URL(url)
    requests.push({ url: parsed, options })
    if (parsed.pathname.endsWith('.png')) return new Response('png', { headers: { 'Content-Type': 'image/png' } })
    if (parsed.pathname.endsWith('.pdf')) return new Response('pdf', { headers: { 'Content-Type': 'application/pdf' } })
    if (parsed.pathname.endsWith('.xlsx')) return new Response('xlsx', { headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' } })
    return new Response('{}', { headers: { 'Content-Type': 'application/json' } })
  })
  const query = { preset: 'today', date_from: '2026-10-10', date_to: '2026-10-10' }
  await api.liveTourCollection('pending', query)
  await api.liveTourReports(query)
  await api.liveTourBoardHistory(query)
  await api.liveTourCustomerHistory('customer-1', query)
  await api.exportLiveTourExcel('paid', query)
  await api.exportLiveTourBoardHistory(query)
  await api.readCustomerCountPdf(query)
  await api.readCustomerCountPng(query)
  assert.equal(requests.length, 8)
  for (const { url } of requests) assert.equal(url.searchParams.get('preset'), 'today', url.pathname)
})

test('permission-scoped cancellation prevents an Excel file from downloading after its blob read', async () => {
  const controller = new AbortController()
  const { api, downloads } = apiFixture(async () => ({ ok: true, headers: new Headers(), blob: async () => {
    controller.abort()
    return new Blob(['old-authorized-workbook'])
  } }))
  await assert.rejects(api.exportLiveTourExcel('paid', { preset: 'all' }, { signal: controller.signal }), error => error.name === 'AbortError')
  assert.equal(downloads.length, 0)
})

test('binary authorization errors retain refreshed capabilities and canceled exports never retry', async () => {
  const caps = { date_filters: { version: 1, sections: { reports: ['today'] }, server_today: '2026-10-10' } }
  const first = apiFixture(async () => new Response(JSON.stringify({ detail: { message: 'Preset denied', capabilities: caps } }), { status: 403, headers: { 'Content-Type': 'application/json' } }))
  await assert.rejects(first.api.exportLiveTourExcel('reports', { preset: 'all' }), error => error.status === 403 && JSON.stringify(error.payload.detail.capabilities) === JSON.stringify(caps))
  let calls = 0
  const second = apiFixture((_url, options) => { calls++; return new Promise((_resolve, reject) => options.signal.addEventListener('abort', () => reject(new DOMException('aborted', 'AbortError')), { once: true })) })
  const controller = new AbortController(), pending = second.api.exportLiveTourExcel('reports', { preset: 'all' }, { signal: controller.signal })
  await new Promise(setImmediate)
  controller.abort()
  await assert.rejects(pending, error => error.name === 'AbortError')
  assert.equal(calls, 1)
})
