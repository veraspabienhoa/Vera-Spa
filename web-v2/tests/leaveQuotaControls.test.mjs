import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LeaveListPersonalStats.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'quota-api', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi=globalThis.__quotaApi;', loader: 'js' }))
  } }],
})

async function fixture({ description = '', fail = false, role = 'admin' } = {}) {
  const dom = new JSDOM('<body><section class="leave-list-panel" data-leave-start="2026-09-26" data-leave-end="2026-09-26" data-leave-employee=""><div class="panel-title-row"></div><div class="leave-list-wrap"></div></section><div id="root"></div></body>')
  dom.window.document.querySelector('.panel-title-row').textContent = description
  const calls = [], names = ['window', 'document', 'navigator', 'MutationObserver', 'IS_REACT_ACT_ENVIRONMENT', '__quotaApi']
  const descriptors = Object.fromEntries(names.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  Object.defineProperties(globalThis, {
    window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
    navigator: { value: dom.window.navigator, configurable: true }, MutationObserver: { value: dom.window.MutationObserver, configurable: true },
    IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
    __quotaApi: { configurable: true, value: {
      leaveListStats: async (...args) => { calls.push(['stats', ...args]); return { summary: {}, monthly_allowances: [] } },
      leaveQuotaCheck: async (start, end) => {
        calls.push(['quota', start, end])
        if (fail) throw Error('Kiểm tra tạm thời lỗi')
        return { start, end, limits: { days: 5 }, items: [] }
      },
    } },
  })
  const { createRoot } = await import('react-dom/client')
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(dom.window.document.querySelector('#root'))
  await act(async () => root.render(React.createElement(module.exports.default, { user: { role } })))
  const doc = dom.window.document
  return { doc, calls, button: () => doc.querySelector('.leave-quota-check-button'), recover: () => { fail = false },
    async changeRange(start, end) {
      await act(async () => {
        const panel = doc.querySelector('.leave-list-panel')
        panel.dataset.leaveStart = start; panel.dataset.leaveEnd = end
        await new Promise(resolve => setTimeout(resolve, 70))
      })
    },
    async dispose() {
      await act(() => root.unmount()); dom.window.close()
      for (const [key, descriptor] of Object.entries(descriptors)) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key]
      }
    },
  }
}

for (const description of ['', 'Tháng đang xem: 09-2026. Bộ lọc chỉ áp dụng trong tháng này.']) {
  test(`quota check works without parsing the heading: ${description || 'hidden heading'}`, async () => {
    const f = await fixture({ description })
    try {
      assert.equal(f.button().disabled, false)
      assert.match(f.doc.querySelector('.leave-list-personal-summary-head').textContent, /26-09-2026 – 26-09-2026/)
      await act(async () => f.button().click())
      assert.equal(f.button().parentElement, f.doc.querySelector('.leave-quota-check-result').parentElement)
      assert.equal(f.button().parentElement.querySelector('.stable-feedback'), null)
      assert.deepEqual(f.calls.find(row => row[0] === 'quota'), ['quota', '2026-09-26', '2026-09-26'])
      assert.match(f.doc.body.textContent, /Không phát hiện trường hợp vượt hạn mức/)
      await f.changeRange('2026-10-01', '2026-10-31')
      assert.doesNotMatch(f.doc.body.textContent, /Không phát hiện trường hợp vượt hạn mức/)
      await act(async () => f.button().click())
      assert.deepEqual(f.calls.filter(row => row[0] === 'quota').at(-1), ['quota', '2026-10-01', '2026-10-31'])
    } finally { await f.dispose() }
  })
}

test('quota request error allows another attempt and clears after success', async () => {
  const f = await fixture({ fail: true })
  try {
    await act(async () => f.button().click())
    assert.equal(f.button().disabled, false)
    assert.match(f.doc.body.textContent, /Kiểm tra tạm thời lỗi/)
    f.recover()
    await act(async () => f.button().click())
    assert.doesNotMatch(f.doc.body.textContent, /Kiểm tra tạm thời lỗi/)
  } finally { await f.dispose() }
})

test('an employee without the quota permission does not receive the action', async () => {
  const f = await fixture({ role: 'nhanvien' })
  try { assert.equal(f.button(), null) } finally { await f.dispose() }
})
