import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { JSDOM } from 'jsdom'
import React, { act } from 'react'
import { EMPTY_TOUR_FILTERS } from '../src/lib/liveTourFilters.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://test.invalid', pretendToBeVisual: true })
for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) Object.defineProperty(globalThis, key, { value, configurable: true })
const { createRoot } = await import('react-dom/client')
async function load(path, plugins = []) {
  const built = await build({ entryPoints: [path], bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime', 'react-dom'], loader: { '.css': 'empty' }, plugins })
  const local = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), local, local.exports)
  return local.exports.default
}
const Filters = await load('src/components/LiveTourFilters.jsx')
const useDetails = await load('src/lib/useLiveTourDetails.js', [{ name: 'api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__permissionApi' }))
} }])
const delay = () => new Promise(resolve => setTimeout(resolve, 210))

test('denied presets, editable date fields and typed arbitrary-date suggestions are absent', async () => {
  const root = createRoot(document.querySelector('#root'))
  let current = { ...EMPTY_TOUR_FILTERS, preset: 'today', date_from: '2026-10-10', date_to: '2026-10-10', employee: 'An' }
  const render = allowedPresets => root.render(React.createElement(Filters, { value: current, rows: [], allowedPresets, serverToday: '2026-10-10', showDate: true, onChange(value) { current = value; render(allowedPresets) } }))
  try {
    await act(() => render(['today', 'week']))
    assert.deepEqual([...document.querySelectorAll('.report-date-buttons button')].map(button => button.textContent), ['Hôm nay', 'Tuần này'])
    assert.equal([...document.querySelectorAll('label')].some(label => ['Từ ngày', 'Đến ngày', 'Ngày'].includes(label.textContent)), false)
    const preset = document.querySelector('.report-date-preset input')
    await act(() => {
      preset.focus()
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(preset, '01011990')
      preset.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    assert.equal([...document.querySelectorAll('[role="option"]')].some(option => option.textContent.includes('01-01-1990')), false)
    await act(() => document.querySelectorAll('.report-date-buttons button')[1].click())
    assert.equal(current.preset, 'week'); assert.equal(current.date_from, '2026-10-05'); assert.equal(current.employee, 'An')
    await act(() => render(['custom']))
    assert.equal([...document.querySelectorAll('label')].some(label => label.textContent === 'Từ ngày'), true)
    assert.equal([...document.querySelectorAll('label')].some(label => label.textContent === 'Ngày'), true)
    await act(() => render([]))
    assert.equal(document.querySelectorAll('.report-date-buttons button').length, 0)
    assert.equal([...document.querySelectorAll('label')].some(label => label.textContent === 'Từ ngày'), false)
  } finally { await act(() => root.unmount()) }
})

test('permission revocation aborts in-flight detail, clears old rows synchronously and blocks late responses', async () => {
  const calls = []
  globalThis.__permissionApi = { liveTourCollection: (panel, query, options) => new Promise(resolve => calls.push({ panel, query, options, resolve })) }
  // The bundled hook captures the fixture object when this function is loaded.
  const Hook = await load('src/lib/useLiveTourDetails.js', [{ name: 'api', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__permissionApi' }))
  } }])
  let latest
  function Probe(props) { latest = Hook(props); return React.createElement('span', null, (latest.data.state?.invoices || []).map(row => row.bill_no).join(',')) }
  const root = createRoot(document.querySelector('#root'))
  const props = { board: { revision: 1, capabilities: {}, state: { invoices: [{ bill_no: 'UNSCOPED-BOARD-INVOICE' }] } }, panel: 'invoices', filters: { preset: 'today' }, authorizationKey: 'account-a:today', lookupOpen: false }
  try {
    await act(() => root.render(React.createElement(Probe, props)))
    assert.equal(document.body.textContent.includes('UNSCOPED'), false)
    await act(delay)
    assert.equal(calls.length, 1)
    await act(async () => calls[0].resolve({ revision: 1, pages: 1, total: 1, data: { state: { invoices: [{ bill_no: 'GRANTED' }] } } }))
    assert.match(document.body.textContent, /GRANTED/)
    await act(() => latest.setPage(2)); await act(delay)
    assert.equal(calls.length, 2)
    await act(() => root.render(React.createElement(Probe, { ...props, authorizationKey: 'account-a:none', readAllowed: false })))
    assert.equal(calls[1].options.signal.aborted, true)
    assert.equal(latest.ready, false); assert.equal(latest.total, 0)
    assert.doesNotMatch(document.body.textContent, /GRANTED|UNSCOPED/)
    await act(async () => calls[1].resolve({ revision: 1, pages: 1, total: 1, data: { state: { invoices: [{ bill_no: 'LATE-DENIED' }] } } }))
    await act(delay)
    assert.equal(calls.length, 2); assert.doesNotMatch(document.body.textContent, /LATE/)
    await act(() => root.render(React.createElement(Probe, { ...props, authorizationKey: 'account-b:today' })))
    assert.equal(latest.ready, false)
    await act(delay)
    assert.equal(calls.length, 3)
  } finally { await act(() => root.unmount()); delete globalThis.__permissionApi }
})

// Keep the original bundled hook exercised even when no requests are permitted.
test('all-denied section makes no network read while leaving reservation lookup scope unchanged', async () => {
  const root = createRoot(document.querySelector('#root'))
  let latest
  function Probe() { latest = useDetails({ board: { revision: 1, state: {} }, panel: 'pending', filters: { preset: '' }, authorizationKey: 'none', readAllowed: false, lookupOpen: false }); return null }
  try { await act(() => root.render(React.createElement(Probe))); await act(delay); assert.equal(latest.ready, false); assert.equal(latest.total, 0) }
  finally { await act(() => root.unmount()) }
})

test('partial custom drafts invalidate the saved range until completed or an authorized preset is chosen', async () => {
  const root = createRoot(document.querySelector('#root'))
  let current = { ...EMPTY_TOUR_FILTERS, preset: 'custom', date_from: '2026-10-01', date_to: '2026-10-10' }, valid = true
  const render = () => root.render(React.createElement(Filters, { value: current, rows: [], allowedPresets: ['today', 'custom'], serverToday: '2026-10-10', showDate: true,
    onValidityChange(value) { valid = value }, onChange(value) { current = value; render() } }))
  const type = async (input, text) => act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, text)
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
  try {
    await act(render)
    const from = [...document.querySelectorAll('label')].find(label => label.textContent === 'Từ ngày').querySelector('input')
    await type(from, '01')
    assert.equal(current.date_from, '2026-10-01', 'input retains saved ISO until complete')
    assert.equal(valid, false, 'parent must not submit that saved value during a partial draft')
    const to = [...document.querySelectorAll('label')].find(label => label.textContent === 'Đến ngày').querySelector('input')
    await type(to, '12102026')
    assert.equal(valid, false, 'completing the other field cannot validate an unfinished draft')
    await act(() => document.querySelector('.report-date-buttons button').click())
    assert.equal(valid, true); assert.equal(current.preset, 'today')
    assert.equal([...document.querySelectorAll('label')].find(label => label.textContent === 'Từ ngày').querySelector('input').value, '10-10-2026')
  } finally { await act(() => root.unmount()) }
})
