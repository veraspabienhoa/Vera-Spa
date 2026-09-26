import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

// React DOM must detect input events against a browser-like document, not Node.
const bootstrap = new JSDOM('<body></body>')
globalThis.window = bootstrap.window
globalThis.document = bootstrap.window.document
after(() => bootstrap.window.close())
const require = createRequire(import.meta.url)
const options = { bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react-dom', 'react/jsx-runtime'], loader: { '.css': 'empty' } }
async function bundle(contents, plugins = []) {
  const result = await build({ ...options, stdin: { contents, loader: 'jsx', resolveDir: process.cwd() }, plugins })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, module, module.exports)
  return module.exports
}
const common = await bundle(`
  export { default as usePageRefresh, requestPageRefresh, PAGE_REFRESH_ERROR } from './src/lib/usePageRefresh';
  export { default as Feedback } from './src/components/StableFeedback';
  export { default as DataRegion } from './src/components/StableDataRegion';
  export { default as ProfileDialog } from './src/components/EmployeeProfileModal';
  export { default as NotificationDialog } from './src/components/NotificationEditorDialog';
`)
const { usePageRefresh, requestPageRefresh, PAGE_REFRESH_ERROR, Feedback, DataRegion } = common
const h = React.createElement
const defer = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }
async function setup(context) {
  const dom = new JSDOM('<body><button id="opener">Mở</button><main></main></body>', { url: 'https://example.test', pretendToBeVisual: true })
  const saved = {}
  for (const [key, value] of Object.entries({ window: dom.window, document: dom.window.document, navigator: dom.window.navigator, IS_REACT_ACT_ENVIRONMENT: true })) {
    saved[key] = Object.getOwnPropertyDescriptor(globalThis, key)
    Object.defineProperty(globalThis, key, { value, configurable: true })
  }
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('main'))
  context.after(async () => {
    await act(() => root.unmount())
    dom.window.close()
    for (const [key, value] of Object.entries(saved)) { if (value) Object.defineProperty(globalThis, key, value); else delete globalThis[key] }
  })
  return { root, render: element => act(async () => root.render(element)) }
}

test('refresh preflight protects every panel, uses current filters, and prevents overlapping loads', async context => {
  const { render } = await setup(context)
  let calls = [], dirty = true, first = defer(), failure = false
  const errors = []
  window.addEventListener(PAGE_REFRESH_ERROR, event => errors.push(event.detail))
  function Panel({ id, filter }) {
    usePageRefresh(async () => { calls.push([id, filter]); if (failure) throw Error('Unavailable'); await first.promise }, () => id === 2 && dirty)
    return h('input', { defaultValue: `draft-${id}` })
  }
  const panels = filter => h('div', null, h(Panel, { id: 1, filter }), h(Panel, { id: 2, filter }))
  await render(panels('09-2026'))
  assert.equal(calls.length, 0, 'registration must not make another initial request')
  assert.equal(requestPageRefresh(), false)
  assert.deepEqual(calls, [], 'one dirty panel vetoes all loaders before any request starts')
  dirty = false
  const input = document.querySelector('main input')
  input.value = 'Nội dung đang nhập'; input.focus()
  await act(async () => { assert.equal(requestPageRefresh(), true); assert.equal(requestPageRefresh(), false) })
  assert.deepEqual(calls, [[1, '09-2026'], [2, '09-2026']])
  await act(async () => first.resolve())
  await render(panels('10-2026'))
  await act(async () => requestPageRefresh())
  assert.deepEqual(calls.slice(-2), [[1, '10-2026'], [2, '10-2026']])
  assert.equal(document.querySelector('main input'), input)
  assert.equal(input.value, 'Nội dung đang nhập')
  assert.equal(document.activeElement, input)
  failure = true
  await act(async () => requestPageRefresh())
  assert.deepEqual(errors, ['Unavailable', 'Unavailable'])
  failure = false; first = defer()
  await act(async () => requestPageRefresh())
  await render(null)
  const before = calls.length
  requestPageRefresh()
  assert.equal(calls.length, before, 'navigated-away pages remove their listeners')
  await act(async () => first.reject(Error('Late failure')))
  assert.equal(errors.length, 2, 'an old page cannot report errors on the next page')
})

test('feedback and loading keep the same table, focus, and horizontal scroll container', async context => {
  const { render } = await setup(context)
  const view = (loading, message) => h('section', null,
    h(Feedback, null, message && h('p', { role: 'status' }, message)),
    h(DataRegion, { loading }, h('div', { className: 'table-scroll' }, h('input', { defaultValue: 'draft' }), h('table', null, h('tbody', null, h('tr', null, h('td', null, 'Saved row')))))))
  await render(view(false, ''))
  const feedback = document.querySelector('.stable-feedback'), table = document.querySelector('table'), scroll = document.querySelector('.table-scroll'), input = document.querySelector('main input')
  input.focus(); input.value = 'Still editing'; scroll.scrollLeft = 360
  for (const [loading, message] of [[true, 'Đang lưu'], [false, 'Đã lưu'], [false, 'Lỗi dài '.repeat(100)], [false, '']]) {
    await render(view(loading, message))
    assert.equal(document.querySelector('.stable-feedback'), feedback)
    assert.equal(document.querySelector('table'), table)
    assert.equal(scroll.scrollLeft, 360)
    assert.equal(input.value, 'Still editing')
    assert.equal(document.querySelector('.stable-data-content').hasAttribute('inert'), loading)
    assert.equal(document.querySelector('.stable-data-region').getAttribute('aria-busy'), String(loading))
    assert.equal(feedback.textContent, message, 'long errors remain readable rather than cut from the DOM')
  }
  // JSDOM has no layout engine: verify the CSS contract, not fictional pixel measurements.
  const css = readFileSync('src/components/StableFeedback.css', 'utf8')
  assert.match(css, /height: 52px/); assert.match(css, /max-height: 52px/)
  assert.match(css, /max-width: 820px/); assert.match(css, /height: 64px/)
  assert.match(css, /overflow: auto/)
  assert.match(readFileSync('src/components/StableDataRegion.css', 'utf8'), /position: absolute/)
  const pageCss = readFileSync('src/page-stability.css', 'utf8')
  assert.match(pageCss, /scrollbar-gutter: stable/); assert.match(pageCss, /overflow-anchor: none/)
  assert.match(pageCss, /\.face-id-card::after[^}]+height: 64px/)
  assert.match(pageCss, /\.face-id-card > \.employee-identity-notice[^}]+position: absolute/s)
})

test('profile and notification dialogs enter and restore focus without scrolling; busy Escape stays protected', async context => {
  const { render } = await setup(context)
  const focused = [], original = window.HTMLElement.prototype.focus
  window.HTMLElement.prototype.focus = function (options) { focused.push({ node: this, options }); return original.call(this, options) }
  const opener = document.querySelector('#opener')
  for (const Dialog of [common.ProfileDialog, common.NotificationDialog]) {
    opener.focus(); focused.length = 0
    let closes = 0
    const dialog = busy => h(Dialog, { busy, title: 'Sửa', onClose: () => { closes++ } }, h('input', { defaultValue: 'draft' }))
    await render(dialog(false))
    assert.equal(focused.at(-1).options.preventScroll, true)
    await render(dialog(true))
    const node = document.querySelector('[role=dialog]')
    await act(async () => {
      node.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
      node.dispatchEvent(new window.Event('cancel', { cancelable: true }))
    })
    assert.equal(closes, 0)
    await render(null)
    assert.equal(document.activeElement, opener)
    assert.equal(focused.at(-1).options.preventScroll, true)
    assert.equal(document.body.style.overflow, '')
  }
})

const app = await bundle("export { default } from './src/App';", [{ name: 'app-boundaries', setup(b) {
  b.onResolve({ filter: /^\.\// }, args => args.path === './src/App' || /\/(usePageRefresh|sharedRead|pageModuleLoader|recoverablePage|PageErrorBoundary)(\.js)?$/.test(args.path) ? undefined : ({ path: args.path, namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ loader: 'jsx', resolveDir: process.cwd(), contents:
    path.endsWith('/api') ? 'export const veraApi={me:async()=>({employee_username:"synthetic",role:"admin"})};' :
    path.endsWith('/supabase') ? 'export const isAuthConfigured=true;export const getCurrentSession=async()=>({access_token:"synthetic",user:{id:"u"}});export const onVeraAuthStateChange=()=>()=>{};export const signOutVera=async()=>{};' :
    path.endsWith('/pushNotifications') ? 'export const ensureGrantedPushSubscription=async()=>{};' :
    path.endsWith('/AppShell') ? 'export default function Shell({children,onRefreshCurrentPage,onPageChange}){return <><button id="refresh" onClick={onRefreshCurrentPage}>Refresh</button><button id="navigate" onClick={()=>onPageChange("employees")}>Employees</button>{children(null)}</>}' :
    path.includes('/pages/LiveTourPage') || path.includes('/pages/EmployeePage') ? `
      import {useEffect,useState} from 'react';
      import usePageRefresh from '${process.cwd()}/src/lib/usePageRefresh.js';
      export default function Page(){const [filter,setFilter]=useState('');const [n,setN]=useState(0);usePageRefresh(()=>setN(x=>x+1));useEffect(()=>{window.mountCount=(window.mountCount||0)+1},[]);return <><input id="filter" value={filter} onChange={e=>setFilter(e.target.value)}/><output>{n}</output></>}
    ` : 'export default function Stub(){return null}',
  }))
} }])
test('actual App header refresh keeps the active page mounted; explicit navigation still changes the page', async context => {
  const { render } = await setup(context)
  await render(h(app.default))
  const input = document.querySelector('#filter')
  assert.ok(input)
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, 'An An')
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
  input.focus()
  await act(async () => document.querySelector('#refresh').click())
  assert.equal(window.mountCount, 1)
  assert.equal(document.querySelector('#filter'), input)
  assert.equal(input.value, 'An An')
  assert.equal(document.activeElement, input)
  assert.equal(document.querySelector('output').textContent, '1')
  await act(async () => document.querySelector('#navigate').click())
  assert.equal(window.mountCount, 2)
  assert.notEqual(document.querySelector('#filter'), input)
})

const purchase = await bundle("export { default } from './src/pages/PurchasePage';", [{ name: 'purchase-api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi={purchases:q=>window.purchaseLoad(q)};', loader: 'js' }))
} }])
test('real purchase page keeps its table during deferred refresh and preserves filter state', async context => {
  const { render } = await setup(context)
  const response = { rows: [{ id: 'r', purchase_date: '2026-09-26', item: 'Khăn', quantity: 1, unit_price: 20, amount: 20, note: '', entered_by: 'synthetic' }], permissions: {} }
  const queries = []; let pending
  window.purchaseLoad = async query => { queries.push(query); return pending ? pending.promise : response }
  await render(h(purchase.default, { user: { role: 'admin' } }))
  const table = document.querySelector('.purchase-table table'), scroll = document.querySelector('.purchase-table')
  assert.ok(table); scroll.scrollLeft = 200
  pending = defer()
  await act(async () => requestPageRefresh())
  assert.equal(document.querySelector('.purchase-table table'), table)
  assert.equal(scroll.scrollLeft, 200)
  assert.equal(document.querySelector('.stable-data-region').getAttribute('aria-busy'), 'true')
  assert.equal(requestPageRefresh(), false)
  await act(async () => pending.resolve(response))
  assert.deepEqual(queries[1], queries[0])
  assert.equal(document.querySelector('.purchase-table table'), table)
  assert.equal(scroll.scrollLeft, 200)
  assert.equal(document.querySelector('.stable-data-region').getAttribute('aria-busy'), 'false')
})
