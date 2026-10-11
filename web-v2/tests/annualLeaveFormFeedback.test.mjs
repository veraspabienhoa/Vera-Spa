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
const built = await build({
  stdin: { contents: `export { default } from './src/components/LongLeaveSection'; export { startSystemFeedback } from './src/lib/systemFeedback';`, resolveDir: fileURLToPath(new URL('..', import.meta.url)), loader: 'js' },
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  define: { 'import.meta.env.VITE_VERA_API_BASE_URL': '"https://api.test"' },
  plugins: [{ name: 'session', setup(b) {
    b.onResolve({ filter: /(?:\/|^)supabase$/ }, () => ({ path: 'session', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ loader: 'js', contents: `
      export const isSupabaseConfigured = false; export const supabase = null;
      export async function getCurrentSession() { return globalThis.__annualFormSession ? globalThis.__annualFormSession() : { access_token: 'test' } }
      export async function refreshCurrentSession(session) { globalThis.__annualFormRefreshCalls = (globalThis.__annualFormRefreshCalls || 0) + 1; return session }
    ` }))
  } }],
})
const module = { exports: {} }
new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
const Component = module.exports.default
const response = (payload, status = 200) => ({ ok: status < 400, status, json: async () => payload })
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const employee = { id: 'employee', role: 'nhanvien', employee_username: 'Employee', permissions: { long_leave_form: true } }
const admin = { id: 'admin', role: 'admin', employee_username: 'Admin' }
const row = { id: 'approved', revision: 3, employee_name: 'Employee', request_type: 'Nghỉ Phép năm', start_date: '2026-10-01', end_date: '2026-10-07', days: 7, detail: 'Original detail' }
const overview = (extra = {}) => ({ can_submit: true, can_submit_resignation: true, approved_requests: [row], resignation_requests: [], ...extra })
const buttons = (scope = document) => [...scope.querySelectorAll('button')]
const button = (text, scope = document) => buttons(scope).find(node => node.textContent.trim() === text)
const modal = () => document.querySelector('.system-dialog')
const message = () => modal()?.querySelector('.system-dialog-message')?.textContent || ''
const writes = calls => calls.filter(call => call.method !== 'GET')
const click = async node => { assert.ok(node, 'expected button'); await act(async () => node.click()) }
const close = async () => { await click(button('Đóng', modal())); assert.equal(modal(), null) }
const escape = async () => { await act(async () => document.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))) }
const submit = async (selector, twice = false) => {
  await act(async () => {
    const form = document.querySelector(selector)
    form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
    if (twice) form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
  })
}
const change = async (node, value) => {
  assert.ok(node, 'expected form field')
  await act(async () => {
    const prototype = node.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(node, value)
    node.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
}
async function fixture(user, handler = () => undefined) {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), calls = []
  const stopFeedback = module.exports.startSystemFeedback(document)
  globalThis.fetch = async (url, options = {}) => {
    const call = { url, method: options.method || 'GET', options }
    calls.push(call)
    const result = handler(call)
    if (result !== undefined) return result
    return response(url.endsWith('/pending-changes') ? { request_ids: [] } : overview())
  }
  const render = async (nextUser = user, extra = {}) => { await act(async () => root.render(React.createElement(Component, { user: nextUser, ...extra }))) }
  await render()
  return { calls, render, destroy: async () => {
    delete globalThis.__annualFormSession
    delete globalThis.__annualFormRefreshCalls
    await act(async () => root.unmount())
    globalThis.fetch = original
    try { assert.equal(modal(), null, 'unmount removes owned feedback and decisions') } finally { stopFeedback() }
  } }
}

test('create error stays in modal until Close and preserves form; retry deduplicates and success contains warnings', async () => {
  const wait = deferred(); let attempts = 0
  const f = await fixture(employee, call => {
    if (call.method === 'POST') return ++attempts === 1 ? response({ detail: 'Không đủ quỹ phép.' }, 400) : wait.promise
  })
  try {
    const textarea = document.querySelector('.long-leave-form textarea')
    await change(textarea, 'Giữ ghi chú này')
    await submit('.long-leave-form')
    assert.equal(modal().dataset.systemDialog, 'error')
    assert.match(message(), /Không đủ quỹ phép/)
    assert.equal(textarea.value, 'Giữ ghi chú này')
    assert.equal(document.querySelector('.long-leave-notice, .action-success-dialog, [role="alert"]'), null)
    await f.render(employee)
    assert.match(message(), /Không đủ quỹ phép/)
    await close()
    assert.equal(textarea.value, 'Giữ ghi chú này')
    await f.render(employee)
    assert.equal(modal(), null, 'ordinary rerender must not replay dismissed error')
    await submit('.long-leave-form', true)
    assert.equal(attempts, 2)
    assert.equal(document.querySelector('.long-leave-submit').disabled, true)
    await act(async () => wait.resolve(response({ message: 'Đã gửi đơn chờ duyệt.', request_id: 'NEW-7', warnings: ['Lưu ý đầy đủ.'] })))
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.match(message(), /Đã gửi đơn chờ duyệt.*NEW-7.*Lưu ý đầy đủ/)
    assert.equal(textarea.value, '')
    assert.equal(writes(f.calls).length, 2)
    assert.ok(writes(f.calls).every(call => call.url.endsWith('/long-leave/requests')))
    await close()
  } finally { await f.destroy() }
})

test('load error is a modal and eligibility/pause remain persistent data across refresh and dismissal', async () => {
  let failed = true
  const f = await fixture(employee, call => call.url.endsWith('/overview') ? response(failed ? { detail: 'Không tải được phép năm.' } : overview({ paused: true, pause_message: 'Tạm dừng nhận đơn', eligibility: { allowed: false, message: 'Chưa đến kỳ phép' } }), failed ? 500 : 200) : undefined)
  try {
    assert.equal(modal().dataset.systemDialog, 'error')
    assert.match(message(), /Không tải được phép năm/)
    await close()
    failed = false
    await click(button('Làm mới'))
    assert.equal(modal(), null)
    const gates = document.querySelectorAll('.long-leave-gate[data-feedback-inline]')
    assert.equal(gates.length, 2)
    assert.match(gates[1].textContent, /Chưa đến kỳ phép/)
    assert.equal(writes(f.calls).length, 0)
  } finally { await f.destroy() }
})

test('return validation, confirmation Escape, failure and success use modals without duplicate writes or lost drafts', async () => {
  let fail = true
  const f = await fixture(admin, call => call.url.endsWith('/return-to-work') ? response(fail ? { detail: 'Ngày quay lại chưa hợp lệ.' } : { message: 'Đã kết thúc kỳ nghỉ.' }, fail ? 400 : 200) : undefined)
  try {
    const cell = document.querySelector('.long-leave-return-cell'), finish = button('Kết thúc kỳ nghỉ', cell)
    await act(async () => { finish.click(); finish.click() })
    assert.equal(document.querySelectorAll('.system-dialog').length, 1)
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.match(message(), /ngày quay lại hợp lệ và ghi chú/)
    await close()
    await change(cell.querySelector('[aria-label="Ngày quay lại làm việc"]'), '08-10-2026')
    await change(cell.querySelector('[placeholder="Ghi chú đã quay lại"]'), 'Đã quay lại ca sáng')
    await act(async () => { finish.click(); finish.click() })
    assert.equal(document.querySelectorAll('.system-dialog-confirm').length, 1)
    await escape()
    assert.equal(modal(), null)
    assert.equal(writes(f.calls).length, 0)
    await click(finish)
    await click(button('Xác nhận', modal()))
    assert.equal(modal().dataset.systemDialog, 'error')
    assert.match(message(), /Ngày quay lại chưa hợp lệ/)
    await close()
    assert.equal(cell.querySelector('[placeholder="Ghi chú đã quay lại"]').value, 'Đã quay lại ca sáng')
    await change(cell.querySelector('[aria-label="Ngày quay lại làm việc"]'), '09-10-20')
    await click(finish)
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.equal(writes(f.calls).length, 1)
    await close()
    await change(cell.querySelector('[aria-label="Ngày quay lại làm việc"]'), '09-10-2026')
    fail = false
    await click(finish)
    await click(button('Xác nhận', modal()))
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.match(message(), /Đã kết thúc kỳ nghỉ/)
    assert.equal(writes(f.calls).length, 2)
    assert.equal(JSON.parse(writes(f.calls)[1].options.body).return_date, '2026-10-09')
    await close()
  } finally { await f.destroy() }
})

test('approved edit failure keeps its editor and drafts through modal Close; successful retry saves once', async () => {
  const wait = deferred(); let count = 0
  const f = await fixture(admin, call => call.method === 'PUT' ? (++count === 1 ? response({ detail: 'Đơn đã thay đổi, vui lòng kiểm tra.' }, 409) : wait.promise) : undefined)
  try {
    await click(button('Sửa đơn'))
    await change(document.querySelector('.approved-request-editor textarea'), 'Chi tiết đã sửa')
    await submit('.approved-request-editor form')
    assert.equal(modal().dataset.systemDialog, 'error')
    await close()
    assert.equal(document.querySelector('.approved-request-editor textarea').value, 'Chi tiết đã sửa')
    await submit('.approved-request-editor form', true)
    assert.equal(count, 2)
    await act(async () => wait.resolve(response({ message: 'Đã lưu thay đổi.', mirror_pending: false })))
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.equal(document.querySelector('.approved-request-editor'), null)
    assert.equal(JSON.parse(writes(f.calls)[1].options.body).detail, 'Chi tiết đã sửa')
    await close()
  } finally { await f.destroy() }
})

test('cancel prompt can close without a write, deduplicates decisions and shows error/success in the shared modal', async () => {
  let fail = true
  const f = await fixture(admin, call => call.method === 'DELETE' ? response(fail ? { detail: 'Chưa hủy được đơn.' } : { message: 'Đã hủy đơn.', mirror_pending: false }, fail ? 400 : 200) : undefined)
  try {
    await act(async () => { const cancel = button('Hủy đơn'); cancel.click(); cancel.click() })
    assert.equal(document.querySelectorAll('.system-dialog-prompt').length, 1)
    await escape()
    assert.equal(writes(f.calls).length, 0)
    await click(button('Hủy đơn'))
    await change(modal().querySelector('input'), 'Lý do hủy chính xác')
    await click(button('Xác nhận', modal()))
    assert.equal(modal().dataset.systemDialog, 'error')
    await close()
    fail = false
    await click(button('Hủy đơn'))
    await change(modal().querySelector('input'), 'Lý do hủy chính xác')
    await click(button('Xác nhận', modal()))
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.equal(writes(f.calls).length, 2)
    assert.equal(JSON.parse(writes(f.calls)[1].options.body).note, 'Lý do hủy chính xác')
    await close()
  } finally { await f.destroy() }
})

test('sync errors and pending warning remain modal; successful retry removes only pending-sync action', async () => {
  let count = 0
  const f = await fixture(admin, call => {
    if (call.url.endsWith('/pending-changes')) return response({ request_ids: ['approved'] })
    if (call.url.endsWith('/sync')) return ++count === 1 ? response({ detail: 'Lỗi đồng bộ.' }, 500) : response({ mirror_pending: count === 2 })
  })
  try {
    await click(button('Đồng bộ lại đơn approved'))
    assert.equal(modal().dataset.systemDialog, 'error')
    await close()
    await click(button('Đồng bộ lại đơn approved'))
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.match(message(), /Dữ liệu máy chủ đã được lưu/)
    await close()
    await click(button('Đồng bộ lại đơn approved'))
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.equal(button('Đồng bộ lại đơn approved'), undefined)
    assert.ok(document.querySelector('.approved-leave-panel'))
    await close()
  } finally { await f.destroy() }
})

test('account/permission changes abort old loads and suppress stale data and failure feedback', async () => {
  const wait = deferred(); let old = true, signal
  const f = await fixture(admin, call => {
    if (old && call.url.endsWith('/overview')) { signal = call.options.signal; return wait.promise }
  })
  try {
    old = false
    await f.render({ ...admin, id: 'new-admin' })
    assert.equal(signal.aborted, true)
    await act(async () => wait.resolve(response({ detail: 'STALE PRIVATE ERROR' }, 500)))
    assert.equal(modal(), null)
    assert.ok(!document.body.textContent.includes('STALE'))
    const count = f.calls.length
    await f.render({ ...admin, role: 'nhanvien', permissions: {} })
    assert.equal(document.querySelector('.long-leave-section'), null)
    assert.equal(f.calls.length, count)
  } finally { await f.destroy() }
})

test('pending cancellation closes on account switch; delayed authentication cannot send an old decision as a new account', async () => {
  const session = deferred()
  const f = await fixture(admin)
  try {
    await click(button('Hủy đơn'))
    await f.render({ ...admin, id: 'another-admin' })
    assert.equal(modal(), null)
    assert.equal(writes(f.calls).length, 0)
    await click(button('Hủy đơn'))
    await change(modal().querySelector('input'), 'Một lý do')
    let requested = false
    globalThis.__annualFormSession = () => { requested = true; return session.promise }
    await click(button('Xác nhận', modal()))
    assert.equal(requested, true)
    delete globalThis.__annualFormSession
    await f.render({ ...admin, id: 'third-admin' })
    await act(async () => session.resolve({ access_token: 'new-session' }))
    assert.equal(writes(f.calls).length, 0)
    assert.equal(modal(), null)
  } finally { await f.destroy() }
})

test('unmounted create cannot show late success or error and unmount closes existing feedback', async () => {
  const wait = deferred(); let signal
  const f = await fixture(employee, call => {
    if (call.method === 'POST') { signal = call.options.signal; return wait.promise }
  })
  try {
    await submit('.long-leave-form')
    await f.render({ ...employee, id: 'new-employee' })
    assert.equal(signal.aborted, true)
    await act(async () => wait.resolve(response({ message: 'STALE SUCCESS', request_id: 'OLD' })))
    assert.equal(modal(), null)
    assert.ok(!document.body.textContent.includes('STALE'))
    assert.equal(writes(f.calls).length, 1)
  } finally { await f.destroy() }
})

test('partial dates and missing required form values show scoped warnings without submitting old values', async () => {
  const f = await fixture(employee)
  try {
    const date = document.querySelector('.long-leave-form [aria-label="Từ ngày Phép năm"]')
    await change(date, '12-10-20')
    await click(document.querySelector('.long-leave-submit'))
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.equal(writes(f.calls).length, 0)
    await close()
    assert.equal(date.value, '12-10-20')
    assert.equal(document.activeElement, date)
    await change(date, `12-10-${new Date().getFullYear() + 1}`)
    await click(button('ĐƠN XIN NGHỈ LÀM ĐẸP'))
    await click(document.querySelector('.long-leave-submit'))
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.match(message(), /Vui lòng nhập lý do nghỉ làm đẹp/)
    assert.equal(writes(f.calls).length, 0)
    await f.render({ ...employee, id: 'another-employee' })
    assert.equal(modal(), null, 'native-validation warnings belong to their account')
  } finally { await f.destroy() }
})

test('approved-editor invalid partial date stays intact after closing its warning', async () => {
  const f = await fixture(admin)
  try {
    await click(button('Sửa đơn'))
    const date = document.querySelector('.approved-request-editor .vera-date-input input[type="text"]')
    await change(date, '02-10-20')
    await click(button('Lưu thay đổi'))
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.equal(writes(f.calls).length, 0)
    await close()
    assert.equal(date.value, '02-10-20')
    assert.ok(document.querySelector('.approved-request-editor'))
  } finally { await f.destroy() }
})

test('permission removal cancels an in-flight submission and suppresses even an abort-insensitive error', async () => {
  const wait = deferred(); let signal
  const f = await fixture(employee, call => {
    if (call.method === 'POST') { signal = call.options.signal; return wait.promise }
  })
  try {
    await submit('.long-leave-form')
    await f.render({ ...employee, permissions: { long_leave_stats: true } })
    assert.equal(signal.aborted, true)
    assert.equal(document.querySelector('.long-leave-form'), null)
    await act(async () => wait.resolve(response({ detail: 'STALE PERMISSION ERROR' }, 403)))
    assert.equal(modal(), null)
    assert.ok(!document.body.textContent.includes('STALE'))
  } finally { await f.destroy() }
})

test('successful create and failed reload retain both modal notices in order without submitting again', async () => {
  let loads = 0
  const f = await fixture(employee, call => {
    if (call.method === 'POST') return response({ message: 'Đã gửi đơn chờ duyệt.', request_id: 'SAVED' })
    if (call.url.endsWith('/overview') && ++loads > 1) return response({ detail: 'Chưa tải lại được danh sách.' }, 500)
  })
  try {
    await submit('.long-leave-form')
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.match(message(), /SAVED/)
    await click(button('Đóng', modal()))
    assert.equal(modal().dataset.systemDialog, 'error')
    assert.match(message(), /Chưa tải lại được danh sách/)
    await close()
    assert.equal(writes(f.calls).length, 1)
    assert.equal(document.querySelector('.long-leave-form textarea').value, '')
  } finally { await f.destroy() }
})

test('a late 401 from a switched account cannot refresh old credentials or retry its write', async () => {
  const wait = deferred()
  const f = await fixture(employee, call => call.method === 'POST' ? wait.promise : undefined)
  try {
    globalThis.__annualFormSession = () => ({ access_token: 'old-access', refresh_token: 'old-refresh' })
    await submit('.long-leave-form')
    delete globalThis.__annualFormSession
    await f.render({ ...employee, id: 'new-employee' })
    await act(async () => wait.resolve(response({ detail: 'Old session expired' }, 401)))
    assert.equal(globalThis.__annualFormRefreshCalls || 0, 0)
    assert.equal(writes(f.calls).length, 1)
    assert.equal(modal(), null)
  } finally { await f.destroy() }
})

test('resignation-only role keeps its authorized form after a successful modal and stats-only role exposes no form', async () => {
  const resignationUser = { ...employee, permissions: { resignation_form: true } }
  const future = `${new Date().getFullYear() + 1}-12-01`
  const f = await fixture(resignationUser, call => {
    if (call.method === 'POST') return response({ message: 'Đã gửi đơn nghỉ việc.', request_id: 'RESIGN' })
    if (call.url.endsWith('/overview')) return response(overview({ resignation_eligibility: { allowed: true, earliest_resignation_date: future, message: 'Được gửi đơn nghỉ việc' } }))
  })
  try {
    assert.equal(document.querySelector('.long-leave-type-tabs').textContent.trim(), 'ĐƠN XIN NGHỈ VIỆC')
    assert.match(document.querySelector('.long-leave-submit').textContent, /Nghỉ việc/)
    assert.equal(document.querySelector('.approved-leave-panel'), null)
    await change(document.querySelector('[aria-label="Ngày nghỉ việc dự kiến"]'), `01-12-${new Date().getFullYear() + 1}`)
    await change(document.querySelector('.long-leave-form textarea'), 'Bàn giao đầy đủ')
    await click(document.querySelector('.long-leave-submit'))
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.equal(JSON.parse(writes(f.calls)[0].options.body).request_type, 'Nghỉ việc')
    await close()
    assert.match(document.querySelector('.long-leave-submit').textContent, /Nghỉ việc/)
    assert.ok(document.querySelector('[aria-label="Ngày nghỉ việc dự kiến"]'))
    assert.equal(document.querySelector('.long-leave-form textarea').value, '')
    assert.equal(modal(), null, 'eligibility status must remain inline')
    await f.render({ ...employee, permissions: { long_leave_stats: true } })
    assert.equal(document.querySelector('form'), null)
    assert.ok(document.querySelector('.approved-leave-panel'))
    assert.equal(button('Hủy đơn'), undefined)
    assert.equal(button('Sửa đơn'), undefined)
    assert.equal(writes(f.calls).length, 1)
  } finally { await f.destroy() }
})

test('form errors retain category routing while success and native validation do not add notifications', async () => {
  const categories = [], capture = event => categories.push(event.detail.category)
  window.addEventListener('vera-system-feedback', capture)
  let fail = true
  const f = await fixture(employee, call => call.method === 'POST' ? response(fail ? { detail: 'Không đủ quỹ phép.' } : { message: 'Đã gửi đơn.', request_id: 'new' }, fail ? 400 : 200) : undefined)
  try {
    await submit('.long-leave-form')
    assert.deepEqual(categories, ['ui_error'])
    await close(); fail = false
    await submit('.long-leave-form')
    assert.deepEqual(categories, ['ui_error'])
    await close()
    await change(document.querySelector('.long-leave-form input[type="text"]:not([disabled]):not([readonly])'), '12')
    await submit('.long-leave-form')
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.deepEqual(categories, ['ui_error'])
    await close()
  } finally { window.removeEventListener('vera-system-feedback', capture); await f.destroy() }
})
