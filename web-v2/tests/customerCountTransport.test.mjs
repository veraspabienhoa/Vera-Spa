import assert from 'node:assert/strict'
import test from 'node:test'
import vm from 'node:vm'
import { build } from 'esbuild'
const built = await build({
  stdin: { contents: "export { veraApi } from './src/lib/api';", resolveDir: process.cwd() }, bundle: true, write: false, platform: 'node', format: 'cjs',
  define: { 'import.meta.env': '{"VITE_VERA_API_BASE_URL":"https://api.example.test"}' },
  plugins: [{ name: 'auth-fixture', setup(b) {
    b.onResolve({ filter: /(^|\/)supabase$/ }, () => ({ path: 'auth', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const getCurrentSession = async () => null; export const refreshCurrentSession = async () => null; export const isSupabaseConfigured = false; export const supabase = null;' }))
  } }],
})
function apiFixture(fetch) {
  const context = vm.createContext({ module: { exports: {} }, fetch, Headers, AbortController, AbortSignal, URL, URLSearchParams, structuredClone, setTimeout, clearTimeout })
  context.exports = context.module.exports; vm.runInContext(built.outputFiles[0].text, context); return context.module.exports.veraApi
}
test('PDF and PNG carry identical full-report filters, preserve zero and ignore UI pagination', async () => {
  const requests = [], api = apiFixture(async (url, options) => { requests.push({ url: new URL(url), options }); return new Response('report-bytes', { headers: { 'Content-Type': url.includes('.png?') ? 'image/png' : 'application/pdf' } }) })
  const filters = { date_from: '2026-10-01', date_to: '2026-10-31', date: '2026-10-03', employee: ' Mạnh Đạt ', customer: ' Khách ', service: ' Body ', bill_no: ' HD ', total_amount: 0, page: 9, page_size: 100, selected_ids: ['one'] }, controller = new AbortController()
  assert.equal((await api.readCustomerCountPdf(filters, { signal: controller.signal })).type, 'application/pdf'); assert.equal((await api.readCustomerCountPng(filters, { signal: controller.signal })).type, 'image/png')
  assert.deepEqual(requests.map(request => request.url.pathname), ['/v2/live-tour/customer-count.pdf', '/v2/live-tour/customer-count.png'])
  for (const request of requests) {
    assert.deepEqual(Object.fromEntries(request.url.searchParams), { date_from: '2026-10-01', date_to: '2026-10-31', date: '2026-10-03', employee: 'Mạnh Đạt', customer: 'Khách', service: 'Body', bill_no: 'HD', total_amount: '0' })
    assert.equal(request.options.cache, 'no-store'); assert.equal(request.options.signal, controller.signal)
  }
  controller.abort(); assert.ok(requests.every(request => request.options.signal.aborted))
})
test('PNG transport rejects wrong MIME, empty images and server errors', async () => {
  for (const [body, type] of [['<html>Error</html>', 'text/html'], ['', 'image/png']]) {
    const api = apiFixture(async () => new Response(body, { headers: { 'Content-Type': type } })); await assert.rejects(api.readCustomerCountPng(), /PNG hợp lệ/)
  }
  const api = apiFixture(async () => new Response(JSON.stringify({ detail: 'Báo cáo quá lớn. Hãy chọn khoảng ngày ngắn hơn.' }), { status: 503, headers: { 'Content-Type': 'application/json' } }))
  await assert.rejects(api.readCustomerCountPng(), error => error.status === 503 && /Báo cáo quá lớn/.test(error.message))
})
