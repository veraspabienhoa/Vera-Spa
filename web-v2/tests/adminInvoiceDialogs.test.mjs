import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

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
