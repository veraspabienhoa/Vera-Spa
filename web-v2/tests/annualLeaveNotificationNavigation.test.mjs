import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { notificationPage } from '../src/lib/notificationNavigation.js'

const require = createRequire(import.meta.url)
const annual = { id: 42, created_at: '2026-10-11T01:00:00Z', payload: {
  kind: 'long_leave_requests', title: 'Có Nghỉ Phép năm mới',
  body: 'Nhân viên thử nghiệm · 01-12-2026 đến 07-12-2026. Mở mục Phép năm để duyệt.',
  url: 'https://untrusted.invalid/',
} }
const other = { ...annual, id: 43, payload: { ...annual.payload, kind: 'admin_leave_changes', title: 'Thay đổi đăng ký nghỉ' } }
const admin = { id: 'admin-fixture', employee_username: 'Admin Fixture', role: 'admin', permissions: {} }
const built = await build({
  stdin: { contents: `export {default as App} from './src/App'; export {default as Popup} from './src/components/PopupNotifications'; export {default as Inbox} from './src/components/NotificationInbox'; export {refreshNotificationFeed} from './src/lib/notificationFeed'; export {clearSystemDialogs} from './src/lib/systemDialogs';`, resolveDir: process.cwd() },
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'react-dom/client', 'lucide-react'], loader: { '.css': 'empty' },
  define: { 'import.meta.env': '{"VITE_VERA_API_BASE_URL":"https://api.invalid"}' },
  plugins: [{ name: 'offline-api-fixtures', setup(b) {
    b.onResolve({ filter: /\/(api|supabase)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ loader: 'js', contents: path === 'api'
      ? 'export const apiRequest=async()=>({}); export const apiBinaryResponse=async()=>new Response(); export const isApiConfigured=true; export const isReadConfigured=true; export const veraApi=globalThis.__notificationApi; export const quangNgaiApi=globalThis.__notificationApi;'
      : `export const isAuthConfigured=true;export const isSupabaseConfigured=false;export const supabase=null;
        export const getCurrentSession=async()=>({access_token:'synthetic',user:{id:'admin-fixture'}});
        export const refreshCurrentSession=getCurrentSession;
        export const onVeraAuthStateChange=callback=>{globalThis.__authChange=callback;return()=>{}};
        export const signOutVera=async()=>{};export const signInWithVeraPassword=async()=>{};` }))
  } }],
})

const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
async function fixture({ url = '/', popup = [], inbox = [], overrides = {} } = {}) {
  const dom = new JSDOM('<body><button id="opener">Mở</button><div id="root"></div></body>', { url: `https://example.test${url}`, pretendToBeVisual: true })
  const calls = [], errors = [], observers = []
  const api = {
    me: async () => ({ ...admin, is_active: true }),
    notificationFeed: async () => { calls.push(['feed']); return { settings: [], popup, inbox } },
    trainingNotifications: async () => ({ notifications: [] }),
    notificationDetail: async id => { calls.push(['detail', id]); return [...inbox, ...popup].find(row => String(row.id) === String(id)) },
    readNotification: async id => { calls.push(['read', id]); popup = popup.filter(row => row.id !== id); inbox = inbox.filter(row => row.id !== id); return { ok: true } },
    notificationSettings: async () => ({ settings: [] }), uiLayout: async () => ({ revision: 1, layout: { desktop: {}, mobile: {} } }),
    longLeaveOverview: async () => { calls.push(['overview']); return { approved_requests: [], resignation_requests: [] } },
    pendingApprovedLongLeave: async () => ({ request_ids: [] }),
    ...overrides,
  }
  const globals = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    localStorage: dom.window.localStorage, sessionStorage: dom.window.sessionStorage,
    getComputedStyle: dom.window.getComputedStyle.bind(dom.window), requestAnimationFrame: dom.window.requestAnimationFrame.bind(dom.window), cancelAnimationFrame: dom.window.cancelAnimationFrame.bind(dom.window),
    __notificationApi: new Proxy(api, { get: (target, key) => target[key] || (async () => ({})) }),
    __authChange: undefined, IS_REACT_ACT_ENVIRONMENT: true,
    fetch: async () => new Response('{"missing":[],"provinces":[],"wards":[],"banks":[]}', { status: 200, headers: { 'Content-Type': 'application/json' } }),
  }
  for (const key of ['MutationObserver', 'HTMLElement', 'Element', 'HTMLInputElement', 'HTMLSelectElement', 'HTMLTextAreaElement', 'Event', 'CustomEvent', 'MouseEvent', 'Node']) globals[key] = dom.window[key]
  globals.MutationObserver = class extends dom.window.MutationObserver { constructor(callback) { super(callback); observers.push(this) } }
  const saved = Object.fromEntries(Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true, writable: true })
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
  window.scrollTo = () => {}
  window.fetch = globals.fetch
  window.HTMLDialogElement.prototype.showModal = function() { this.open = true }
  window.HTMLDialogElement.prototype.close = function() { this.open = false }
  window.addEventListener('error', event => { errors.push(event.error); event.preventDefault() })
  const mod = { exports: {} }; new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, mod, mod.exports)
  const { createRoot } = await import('react-dom/client'), root = createRoot(document.getElementById('root'))
  const settle = async () => { for (let i = 0; i < 4; i++) await act(async () => { await new Promise(resolve => setTimeout(resolve, 15)) }) }
  return { ...mod.exports, calls, errors, root, api, dom, settle,
    async render(Component, props = {}) { await act(async () => root.render(React.createElement(Component, props))); await settle() },
    async click(selector) { const button = document.querySelector(selector); assert.ok(button, selector); await act(async () => button.click()); await settle() },
    async close() { await act(async () => root.unmount()); mod.exports.clearSystemDialogs(); observers.forEach(observer => observer.disconnect()); dom.window.close(); for (const [key, value] of Object.entries(saved)) { if (value) Object.defineProperty(globalThis, key, value); else delete globalThis[key] } },
  }
}

test('only canonical annual-leave category and existing menu permissions produce a destination', () => {
  assert.equal(notificationPage(annual, admin), 'long-leave')
  for (const permission of ['long_leave', 'long_leave_form', 'long_leave_stats', 'resignation_form']) {
    assert.equal(notificationPage(annual, { role: 'nhanvien', permissions: { [permission]: true } }), 'long-leave')
  }
  for (const user of [{ role: 'nhanvien' }, { role: 'admin', must_change_password: true }, { permissions: { long_leave: 'true' } }]) assert.equal(notificationPage(annual, user), '')
  assert.equal(notificationPage(other, admin), '', 'matching words or untrusted URLs must not route a different category')
})

for (const url of ['/', '/?standalone=1&page=live-tour']) test(`actual app opens Phép năm immediately from the shown modal (${url})`, async () => {
  const read = deferred(), f = await fixture({ url, popup: [annual], inbox: [annual], overrides: { readNotification: id => { f.calls.push(['read', id]); return read.promise } } })
  try {
    await f.render(f.App)
    const action = document.querySelector('.popup-notification-open'); assert.ok(action)
    assert.match(action.textContent, /Có Nghỉ Phép năm mới.*Nhân viên thử nghiệm/)
    const beforeHistory = window.history.length
    await act(async () => { action.click(); action.click() }); await f.settle()
    assert.ok(document.querySelector('#long-leave-heading'), 'actual role-scoped annual-leave page renders')
    assert.equal(document.querySelector('.popup-notification'), null)
    assert.equal(document.querySelector('.nav-item.active').textContent, 'Phép năm')
    assert.equal(f.calls.filter(call => call[0] === 'read').length, 1, 'rapid clicks acknowledge once')
    assert.equal(f.calls.filter(call => call[0] === 'overview').length, 1, 'navigation loads the page once')
    assert.equal(f.calls.filter(call => call[0] === 'detail').length, 0, 'popup does not make a redundant detail request')
    assert.equal(f.calls.filter(call => call[0] === 'feed').length, 1, 'popup and inbox share the feed')
    assert.equal(window.history.length, beforeHistory)
    assert.equal(new URL(window.location.href).searchParams.get('page'), url === '/' ? null : 'long-leave')
    assert.match(document.querySelector('.notification-inbox-trigger').getAttribute('aria-label'), /1 chưa đọc/, 'pending acknowledgement does not invent read state')
    f.api.notificationFeed = async () => { f.calls.push(['feed']); return { settings: [], popup: [], inbox: [] } }
    await act(async () => read.resolve({ ok: true })); await f.settle()
    assert.equal(document.querySelector('.notification-unread-dot'), null)
    await f.click('[data-ui-key="u-menu-live-tour"]')
    assert.equal(document.querySelector('#long-leave-heading'), null)
    assert.equal(document.querySelector('.popup-notification'), null, 'returning to Live Tour does not replay the consumed notice')
    assert.deepEqual(f.errors, [])
  } finally { read.resolve({ ok: true }); await f.close() }
})

for (const dismiss of ['.popup-notification [aria-label="Đóng thông báo"]', '.system-dialog-actions .primary-button']) test(`dismiss remains acknowledgement only: ${dismiss}`, async () => {
  const f = await fixture({ popup: [annual] }), destinations = []
  try {
    const opener = document.querySelector('#opener'); opener.focus()
    await f.render(f.Popup, { user: admin, onPageChange: page => destinations.push(page) })
    const button = document.querySelector(dismiss)
    await act(async () => { button.click(); button.click() }); await f.settle()
    assert.deepEqual(destinations, []); assert.deepEqual(f.calls.filter(call => call[0] === 'read'), [['read', 42]])
    assert.equal(document.querySelector('.system-dialog'), null)
    assert.equal(document.activeElement, opener); assert.equal(document.body.style.overflow, '')
  } finally { await f.close() }
})

for (const [row, user] of [[other, admin], [annual, { id: 'employee', role: 'nhanvien' }]]) test(`unrelated or unauthorized popup retains its normal modal (${row.payload.kind}/${user.role})`, async () => {
  const f = await fixture({ popup: [row] }), destinations = []
  try {
    await f.render(f.Popup, { user, onPageChange: page => destinations.push(page) })
    assert.ok(document.querySelector('.system-dialog')); assert.equal(document.querySelector('.popup-notification-open'), null)
    await f.click('.system-dialog-actions .primary-button'); assert.deepEqual(destinations, [])
  } finally { await f.close() }
})

test('popup queue keeps unrelated notices and failed acknowledgement leaves unread feed state intact', async () => {
  const failure = deferred(), f = await fixture({ popup: [annual, other], inbox: [annual], overrides: { readNotification: id => { f.calls.push(['read', id]); return failure.promise } } }), destinations = []
  try {
    await f.render(f.Popup, { user: admin, onPageChange: page => destinations.push(page) })
    await f.click('.popup-notification-open'); assert.deepEqual(destinations, ['long-leave'])
    assert.match(document.querySelector('.system-dialog').textContent, /Thay đổi đăng ký nghỉ/)
    await act(async () => failure.reject(new Error('offline'))); await f.settle()
    assert.equal(f.calls.filter(call => call[0] === 'feed').length, 1, 'failed read does not refresh or claim acknowledgement')
  } finally { failure.resolve({}); await f.close() }
})

test('annual inbox row routes directly while keeping explicit read semantics; other rows keep detail view', async () => {
  const f = await fixture({ inbox: [annual, other] }), destinations = []
  try {
    await f.render(f.Inbox, { user: admin, onPageChange: page => destinations.push(page) })
    await f.click('.notification-inbox-trigger')
    const button = document.querySelector('.notification-row')
    await act(async () => { button.click(); button.click() }); await f.settle()
    assert.deepEqual(destinations, ['long-leave']); assert.equal(document.querySelector('dialog'), null)
    assert.equal(f.calls.filter(call => ['detail', 'read'].includes(call[0])).length, 0)
    assert.match(document.querySelector('.notification-inbox-trigger').getAttribute('aria-label'), /2 chưa đọc/)
    await f.click('.notification-inbox-trigger'); await f.click('.notification-entry + .notification-entry .notification-row')
    assert.match(document.querySelector('.notification-detail').textContent, /Thay đổi đăng ký nghỉ/)
    assert.deepEqual(f.calls.filter(call => call[0] === 'detail'), [['detail', '43']])
    assert.deepEqual(destinations, ['long-leave'])
  } finally { await f.close() }
})

for (const denied of [false, true]) test(`notification deep link waits for scoped detail authorization (denied=${denied})`, async () => {
  const detail = deferred(), f = await fixture({ url: '/?notification=42&standalone=1&page=live-tour', overrides: { notificationDetail: id => { f.calls.push(['detail', id]); return detail.promise } } }), destinations = []
  try {
    window.history.replaceState({ retained: true }, '', window.location.href)
    await f.render(f.Inbox, { user: admin, onPageChange: page => destinations.push(page) })
    assert.deepEqual(destinations, [])
    await act(async () => { if (denied) detail.reject(new Error('No access')); else detail.resolve(annual) }); await f.settle()
    if (denied) { assert.deepEqual(destinations, []); assert.match(document.body.textContent, /No access/); assert.equal(new URL(window.location.href).searchParams.get('notification'), '42') }
    else { assert.deepEqual(destinations, ['long-leave']); assert.equal(document.querySelector('dialog'), null); assert.equal(new URL(window.location.href).searchParams.get('notification'), null); assert.equal(new URL(window.location.href).searchParams.get('page'), 'live-tour'); assert.deepEqual(window.history.state, { retained: true }) }
    assert.equal(f.calls.filter(call => call[0] === 'read').length, 0)
  } finally { detail.resolve(annual); await f.close() }
})

test('closing an in-flight detail or switching accounts cannot navigate from a late response', async () => {
  const detail = deferred(), f = await fixture({ url: '/?notification=42', overrides: { notificationDetail: () => detail.promise } }), destinations = []
  try {
    await f.render(f.Inbox, { key: admin.id, user: admin, onPageChange: page => destinations.push(page) })
    await f.click('[aria-label="Đóng thông báo"]')
    await f.render(f.Inbox, { key: 'new-account', user: { id: 'new-account', role: 'admin' }, onPageChange: page => destinations.push(page) })
    await act(async () => detail.resolve(annual)); await f.settle()
    assert.deepEqual(destinations, []); assert.equal(document.querySelector('dialog'), null)
  } finally { detail.resolve(annual); await f.close() }
})

test('late popup read result cannot refresh a new account', async () => {
  const read = deferred(), f = await fixture({ popup: [annual], overrides: { readNotification: () => read.promise } })
  try {
    await f.render(f.Popup, { key: admin.id, user: admin, onPageChange() {} }); await f.click('.popup-notification-open')
    f.api.notificationFeed = async () => { f.calls.push(['new-account-feed']); return { settings: [], popup: [], inbox: [] } }
    await f.render(f.Popup, { key: 'new-account', user: { ...admin, id: 'new-account' }, onPageChange() {} })
    const count = f.calls.length
    await act(async () => read.resolve({ ok: true })); await f.settle()
    assert.equal(f.calls.length, count); assert.equal(document.querySelector('.system-dialog'), null)
  } finally { read.resolve({}); await f.close() }
})

test('permitted employee reaches their scoped form without Admin approval controls', async () => {
  const employee = { id: 'admin-fixture', employee_username: 'Employee Fixture', role: 'nhanvien', permissions: { long_leave_form: true } }
  const f = await fixture({ popup: [annual], overrides: { me: async () => ({ ...employee, is_active: true }) } })
  try {
    await f.render(f.App); await f.click('.popup-notification-open')
    assert.ok(document.querySelector('.long-leave-form'))
    assert.equal(document.querySelector('.long-leave-employee-field input').value, 'Employee Fixture')
    assert.equal(document.querySelector('.annual-request-admin'), null)
    assert.equal(document.querySelector('.long-leave-admin-panel'), null)
    assert.equal(f.calls.filter(call => call[0] === 'overview').length, 1)
    assert.deepEqual(f.errors, [])
  } finally { await f.close() }
})

for (const action of ['close', 'switch']) test(`late scoped detail cannot route after ${action}`, async () => {
  const detail = deferred(), f = await fixture({ url: '/?notification=42', overrides: { notificationDetail: () => detail.promise } }), destinations = []
  try {
    await f.render(f.Inbox, { key: admin.id, user: admin, onPageChange: page => destinations.push(page) })
    if (action === 'close') await f.click('[aria-label="Đóng thông báo"]')
    else {
      // The next account gets no notification deep link; its feed owns a fresh cache.
      window.history.replaceState({}, '', '/')
      await f.render(f.Inbox, { key: 'new-account', user: { id: 'new-account', role: 'admin' }, onPageChange: page => destinations.push(page) })
    }
    await act(async () => detail.resolve(annual)); await f.settle()
    assert.deepEqual(destinations, []); assert.equal(document.querySelector('dialog'), null)
  } finally { detail.resolve(annual); await f.close() }
})

test('explicit annual inbox acknowledgement dedupes rapid clicks and never navigates', async () => {
  const read = deferred(), f = await fixture({ inbox: [annual], overrides: { readNotification: id => { f.calls.push(['read', id]); return read.promise } } }), destinations = []
  try {
    await f.render(f.Inbox, { user: admin, onPageChange: page => destinations.push(page) }); await f.click('.notification-inbox-trigger')
    const mark = document.querySelector('.notification-viewed')
    await act(async () => { mark.click(); mark.click() }); await f.settle()
    assert.deepEqual(f.calls.filter(call => call[0] === 'read'), [['read', 42]])
    assert.deepEqual(destinations, []); assert.ok(document.querySelector('.notification-entry'))
    f.api.notificationFeed = async () => ({ settings: [], inbox: [], popup: [] })
    await act(async () => read.resolve({ ok: true })); await f.settle()
    assert.equal(document.querySelector('.notification-entry'), null)
    assert.equal(document.querySelector('.notification-unread-dot'), null)
  } finally { read.resolve({}); await f.close() }
})

test('failed inbox acknowledgement retains the annual row and permits one deliberate retry', async () => {
  let attempts = 0
  const f = await fixture({ inbox: [annual], overrides: { readNotification: async () => { attempts++; if (attempts === 1) throw new Error('offline') } } }), destinations = []
  try {
    await f.render(f.Inbox, { user: admin, onPageChange: page => destinations.push(page) }); await f.click('.notification-inbox-trigger')
    await f.click('.notification-viewed')
    assert.ok(document.querySelector('.notification-entry')); assert.match(document.body.textContent, /offline/)
    assert.equal(document.querySelector('.notification-viewed').disabled, false)
    f.api.notificationFeed = async () => ({ settings: [], inbox: [], popup: [] })
    await f.click('.notification-viewed')
    assert.equal(attempts, 2); assert.equal(document.querySelector('.notification-entry'), null); assert.deepEqual(destinations, [])
  } finally { await f.close() }
})

test('annual notification honors the actual employee-page unsaved navigation guard', async () => {
  const employees = [{ username: 'Ánh Mẫu', full_name: 'Nguyễn Ánh Mẫu', role: 'nhanvien', employment_status: 'Đang làm việc', work_shift: 'Ca 1' }]
  const f = await fixture({ url: '/?standalone=1&page=employees', overrides: {
    staff: async () => ({ employees, permissions: { employee_view: true, employee_edit_save: true }, role_options: ['nhanvien'], status_options: ['Đang làm việc'], cycle_options: [], shifts_by_department: {} }),
    employees: async () => ({ employees }), profileReferenceData: async () => ({ provinces: [], wards: [], banks: [] }),
  } })
  try {
    await f.render(f.App)
    await f.click('.staff-table input[aria-label="Không tính lương Ánh Mẫu"]')
    f.api.notificationFeed = async () => ({ settings: [], popup: [annual], inbox: [] })
    await act(async () => f.refreshNotificationFeed()); await f.settle()
    await f.click('.popup-notification-open')
    assert.ok(document.querySelector('.employee-navigation-dialog'), 'notification uses the existing menu guard')
    assert.ok(document.querySelector('.staff-page')); assert.equal(document.querySelector('#long-leave-heading'), null)
    await f.click('.employee-navigation-dialog .secondary-button')
    assert.ok(document.querySelector('.staff-page')); assert.equal(document.querySelector('.employee-navigation-dialog'), null)
    assert.equal(employees[0].payroll_excluded, undefined, 'cancel does not save or discard the underlying draft')
    assert.deepEqual(f.errors, [])
  } finally { await f.close() }
})
