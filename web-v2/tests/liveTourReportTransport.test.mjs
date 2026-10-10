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
