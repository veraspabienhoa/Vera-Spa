import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { defaultTourYesterdayFilters } from '../src/lib/liveTourFilters.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
const dialogs = {}
for (const kind of ['PaidInvoice', 'Pending']) {
  const built = await build({
    entryPoints: [fileURLToPath(new URL(`../src/components/LiveTour${kind}Dialog.jsx`, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  dialogs[kind] = module.exports.default
}

const reportsBuild = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LiveTourReportsPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'api-fixture', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__invoiceReportsApi;', loader: 'js' }))
  } }],
})

for (const role of ['admin', 'letan']) test(`reports page passes ${role} authority to the invoice dialog`, async () => {
  const root = createRoot(document.querySelector('#root'))
  const date = defaultTourYesterdayFilters().date_from
  const item = { id: 'invoice', bill_no: 'TEST-001', business_date: date, effective_at: `${date}T09:00:00+07:00`,
    payment_method: 'TIỀN MẶT', total: 100, entries: [{ employee_name: 'Test', service: 'Body', price: 100 }] }
  const writes = []
  globalThis.__invoiceReportsApi = {
    liveTourReports: async () => ({ revision: 7, invoices: [item], reports: [{ ...item, id: 'report', invoice_id: item.id }],
      capabilities: { paid_invoice_view: true, reports_edit: true, reports_delete: true, invoice_date_edit: false } }),
    liveTourAction: async body => { writes.push(body); return { ok: true } },
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', reportsBuild.outputFiles[0].text)(require, module, module.exports)
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role, permissions: { live_tour_reports_view: true } } })))
    await act(async () => document.querySelector('button[aria-label="Xóa báo cáo và hủy hóa đơn"]').click())
    const dialog = document.querySelector('[role="dialog"]')
    assert.equal(dialog.querySelector('textarea').required, role !== 'admin')
    await act(async () => dialog.querySelector('button[type="submit"]').click())
    assert.equal(writes.length, role === 'admin' ? 1 : 0)
    if (role === 'admin') {
      assert.equal(writes[0].action, 'report_invoice_delete')
      assert.equal(writes[0].payload.reason, '')
      assert.ok(writes[0].idempotency_key)
      assert.equal(writes[0].expected_revision, 7)
    }
  } finally { await act(() => root.unmount()) }
})

for (const kind of ['PaidInvoice', 'Pending']) for (const mode of ['delete', 'edit']) for (const isAdmin of [false, true]) {
  test(`${kind} ${mode}: only admin submits without a reason`, async () => {
    const root = createRoot(document.querySelector('#root'))
    const writes = []
    const props = {
      context: { mode, revision: 7, item: { id: 'old-invoice', bill_no: 'OLD-001', business_date: '2020-01-01',
        effective_at: '2020-01-01T09:00:00+07:00', payment_method: 'TIỀN MẶT', total: 100,
        entries: [{ employee_name: 'Test', service: 'Body', price: 100 }] } },
      catalog: [], isAdmin, canEditDate: isAdmin, busy: false,
      onClose: () => {}, onAction: async (...args) => { writes.push(args); return true },
    }
    try {
      await act(() => root.render(React.createElement(dialogs[kind], props)))
      const reason = [...document.querySelectorAll('label')].find(node => node.textContent.startsWith('Lý do')).querySelector('textarea')
      const submit = document.querySelector('button[type="submit"]')
      assert.equal(reason.required, !isAdmin)
      assert.equal(submit.disabled, !isAdmin)
      if (isAdmin) {
        assert.match(reason.parentNode.textContent, /không bắt buộc/)
        if (kind === 'PaidInvoice' && mode === 'delete') assert.match(document.querySelector('[role="dialog"]').textContent, /số dư và booking combo được giữ nguyên/)
        await act(() => submit.click())
        assert.equal(writes.length, 1)
        assert.equal(writes[0][0], `${kind === 'Pending' ? 'pending' : 'paid_invoice'}_${mode === 'edit' ? 'update' : 'delete'}`)
        assert.equal(writes[0][1].reason, '')
        assert.deepEqual(writes[0][3], { expectedRevision: 7 })
        assert.ok(!('admin_override' in writes[0][1]))
        await act(() => root.render(React.createElement(dialogs[kind], { ...props, busy: true })))
        await act(() => document.querySelector('button[type="submit"]').click())
        assert.equal(writes.length, 1, 'busy form must not submit again')
      } else {
        await act(() => submit.click())
        assert.equal(writes.length, 0)
      }
    } finally { await act(() => root.unmount()) }
  })
}
