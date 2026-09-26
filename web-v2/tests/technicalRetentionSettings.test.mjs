import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/TechnicalRetentionSettings.jsx', import.meta.url))],
  bundle: true, write: false, loader: { '.css': 'empty' }, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime'],
  plugins: [{ name: 'settings-boundaries', setup(b) {
    b.onResolve({ filter: /\/lib\/(supabase|apiConfig)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: path === 'supabase'
      ? 'export const getCurrentSession=async()=>({access_token:"synthetic-token"});'
      : 'export const apiBase="https://api.example.test";', loader: 'js' }))
  } }],
})

async function fixture({ failLoad = false, failSave = false, legacyServer = false } = {}) {
  const dom = new JSDOM('<body><div id="root"></div></body>')
  const names = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', 'fetch']
  const descriptors = Object.fromEntries(names.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const calls = []
  let settings = { days: 2, cleanup_interval_hours: 6, last_cleanup_at: '2026-09-25T15:00:00Z', last_cleanup_removed: 12, next_cleanup_at: '2026-09-25T21:00:00Z' }
  Object.defineProperties(globalThis, {
    window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
    navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
    fetch: { configurable: true, value: async (url, options) => {
      calls.push({ url, ...options })
      if (options.method === 'GET' && failLoad || options.method === 'PUT' && failSave) return { ok: false, status: 503, json: async () => ({ detail: 'Tạm thời không tải được' }) }
      if (options.body) settings = { ...settings, ...JSON.parse(options.body) }
      return { ok: true, json: async () => legacyServer ? { days: settings.days } : settings }
    } },
  })
  const { createRoot } = await import('react-dom/client')
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(dom.window.document.querySelector('#root'))
  await act(async () => root.render(React.createElement(module.exports.default)))
  const doc = dom.window.document
  return { dom, doc, calls, recover: () => { failLoad = false },
    async hours(value) {
      const input = doc.querySelector('#technical-cleanup-hours')
      await act(() => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
        input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
        input.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
      })
    },
    async submit() { await act(async () => doc.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true }))) },
    async dispose() {
      await act(() => root.unmount()); dom.window.close()
      for (const [key, descriptor] of Object.entries(descriptors)) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor)
        else delete globalThis[key]
      }
    },
  }
}

test('loads saved days, interval and Vietnam timestamps, then saves both settings together', async () => {
  const f = await fixture()
  try {
    assert.equal(f.doc.querySelector('#technical-retention-days').value, '2')
    assert.equal(f.doc.querySelector('#technical-cleanup-hours').value, '6')
    assert.match(f.doc.body.textContent, /25-09-2026 22:00:00/)
    assert.match(f.doc.body.textContent, /26-09-2026 04:00:00/)
    await f.hours('3'); await f.submit()
    const writes = f.calls.filter(call => call.method === 'PUT')
    assert.equal(writes.length, 1)
    assert.deepEqual(JSON.parse(writes[0].body), { days: 2, cleanup_interval_hours: 3 })
    assert.match(f.doc.body.textContent, /Chu kỳ đã lưu: mỗi 3 giờ/)
    assert.equal(writes[0].headers.Authorization, 'Bearer synthetic-token')
  } finally { await f.dispose() }
})

test('invalid or empty hours never submit a mutation', async () => {
  const f = await fixture()
  try {
    for (const value of ['', '0', '169', '1.5']) {
      await f.hours(value); await f.submit()
      assert.equal(f.doc.querySelector('button[type="submit"]').disabled, true)
    }
    assert.equal(f.calls.filter(call => call.method === 'PUT').length, 0)
  } finally { await f.dispose() }
})

test('failed loading prevents overwriting server settings with defaults and allows retry', async () => {
  const f = await fixture({ failLoad: true })
  try {
    await f.submit()
    assert.equal(f.doc.querySelector('button[type="submit"]').disabled, true)
    assert.equal(f.calls.length, 1)
    f.recover()
    await act(async () => f.doc.querySelector('button[type="button"]').click())
    assert.equal(f.doc.querySelector('#technical-cleanup-hours').value, '6')
    assert.equal(f.doc.querySelector('button[type="submit"]').disabled, false)
  } finally { await f.dispose() }
})

test('failed save preserves the draft and does not claim it was applied', async () => {
  const f = await fixture({ failSave: true })
  try {
    await f.hours('4'); await f.submit()
    assert.equal(f.doc.querySelector('#technical-cleanup-hours').value, '4')
    assert.match(f.doc.body.textContent, /Chu kỳ đã lưu: mỗi 6 giờ/)
    assert.match(f.doc.body.textContent, /Tạm thời không tải được/)
    assert.doesNotMatch(f.doc.body.textContent, /Đã lưu chu kỳ/)
  } finally { await f.dispose() }
})

test('a frontend deployed before the API cannot claim an unsupported schedule was saved', async () => {
  const f = await fixture({ legacyServer: true })
  try {
    await f.submit()
    assert.equal(f.doc.querySelector('button[type="submit"]').disabled, true)
    assert.equal(f.calls.length, 1)
    assert.match(f.doc.body.textContent, /Deploy VPS Production/)
  } finally { await f.dispose() }
})
