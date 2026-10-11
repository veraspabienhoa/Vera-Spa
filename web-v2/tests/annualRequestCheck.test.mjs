import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const dom = new JSDOM('<body><div id="root"></div></body>',{url:'https://example.test',pretendToBeVisual:true})
Object.defineProperties(globalThis,{window:{value:dom.window,configurable:true},document:{value:dom.window.document,configurable:true},navigator:{value:dom.window.navigator,configurable:true},IS_REACT_ACT_ENVIRONMENT:{value:true,configurable:true}})
const {createRoot}=await import('react-dom/client')
const built=await build({entryPoints:[fileURLToPath(new URL('../src/components/LongLeaveAdminPanel.jsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime','react-dom','lucide-react'],loader:{'.css':'empty'},define:{'import.meta.env.VITE_VERA_API_BASE_URL':'"https://api.test"'},plugins:[{name:'session',setup(b){b.onResolve({filter:/\/lib\/supabase$/},()=>({path:'session',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export async function getCurrentSession(){return globalThis.__annualGetSession ? globalThis.__annualGetSession() : {access_token:"test"}}',loader:'js'}))}}]})
const module={exports:{}}
new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
test('annual card checks its own future dates and shows people and counts without approving',async()=>{
  const original=globalThis.fetch,calls=[],root=createRoot(document.querySelector('#root'))
  globalThis.fetch=async(url,options)=>{
    calls.push([url,options.method||'GET'])
    const data=url.endsWith('/pending')?{requests:[{id:'november',employee_name:'Applicant',request_type:'Nghỉ Phép năm',start_date:'2026-11-20',end_date:'2026-11-26',days:7}]}:
      url.includes('/requests/november/overlap')?{start:'2026-11-20',end:'2026-11-26',employee_count:1,peak_with_applicant:2,days:[{date:'2026-11-21',other_count:1,approved_count:1,pending_count:0}],requests:[{id:'other',employee_name:'Other',full_name:'Employee Test',request_type:'Nghỉ Phép năm',status:'Đã duyệt',start_date:'2026-11-21',end_date:'2026-11-21'}]}:{days:[]}
    return {ok:true,json:async()=>data}
  }
  try{
    await act(async()=>root.render(React.createElement(module.exports.default,{user:{role:'admin'}})))
    assert.ok(!calls.some(([url])=>url.includes('/requests/')))
    const card=document.querySelector('.long-leave-pending-card')
    await act(async()=>[...card.querySelectorAll('button')].find(node=>node.textContent==='Kiểm tra').click())
    assert.equal(calls.filter(([url])=>url.endsWith('/requests/november/overlap')).length,1)
    const result=document.querySelector('.system-dialog')
    assert.equal(card.querySelector('.system-dialog'),null)
    assert.equal(result.getAttribute('aria-modal'),'true')
    assert.match(result.querySelector('h2').textContent,/Kết quả kiểm tra november/)
    assert.match(result.textContent,/1 nhân viên khác nghỉ trong 20-11-2026 – 26-11-2026/)
    assert.match(result.textContent,/Cao nhất 2 người/)
    assert.match(result.textContent,/Employee Test/)
    assert.ok(calls.every(([,method])=>method==='GET'))
  }finally{await act(()=>root.unmount());globalThis.fetch=original}
})

const pendingRow = id => ({ id, employee_name: id, request_type: 'Nghỉ Phép năm', start_date: '2026-12-01', end_date: '2026-12-07', days: 7 })
const checked = (name = 'Other') => ({ start: '2026-12-01', end: '2026-12-07', employee_count: 1, peak_with_applicant: 2, days: [], requests: [{ id: 'other', employee_name: name, request_type: 'Nghỉ Phép năm', status: 'Đã duyệt', start_date: '2026-12-01', end_date: '2026-12-01' }] })
const response = (payload, status = 200) => ({ ok: status < 400, status, json: async () => payload })
const deferred = () => { let resolve; const promise = new Promise(done => { resolve = done }); return { promise, resolve } }
const checkButton = () => [...document.querySelectorAll('.long-leave-pending-card button')].find(node => /Kiểm tra|Đang kiểm tra/.test(node.textContent))

test('rapid checks issue one read and failure can be retried without deciding the request', async () => {
  const original = globalThis.fetch, calls = [], wait = deferred(), root = createRoot(document.querySelector('#root'))
  let checks = 0
  globalThis.fetch = async (url, options) => {
    calls.push([url, options.method || 'GET'])
    if (url.includes('/requests/')) { checks++; return checks === 1 ? wait.promise : response(checked()) }
    return response(url.endsWith('/pending') ? { requests: [pendingRow('target')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', employee_username: 'admin-a' } })))
    await act(async () => { const button = checkButton(); button.click(); button.click() })
    assert.equal(checks, 1)
    assert.equal(checkButton().disabled, true)
    assert.ok([...document.querySelectorAll('.long-leave-decision-row button')].every(button => button.disabled))
    await act(async () => wait.resolve(response({ detail: 'Khoảng ngày của đơn không hợp lệ.' }, 400)))
    assert.match(document.querySelector('.system-dialog-error').textContent, /Khoảng ngày/)
    assert.equal(checkButton().disabled, false)
    await act(async () => document.querySelector('.system-dialog-error button').click())
    await act(async () => checkButton().click())
    assert.equal(checks, 2)
    assert.ok(!document.querySelector('.system-dialog-error'))
    assert.match(document.querySelector('.system-dialog').textContent, /Other/)
    assert.ok(calls.every(([, method]) => method === 'GET'))
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('account switching cancels a check and ignores even an abort-insensitive stale response', async () => {
  const original = globalThis.fetch, wait = deferred(), root = createRoot(document.querySelector('#root'))
  let owner = 'old', oldSignal
  globalThis.fetch = async (url, options) => {
    if (url.includes('/requests/old/overlap')) { oldSignal = options.signal; return wait.promise }
    return response(url.endsWith('/pending') ? { requests: [pendingRow(owner)] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', employee_username: 'old-admin' } })))
    await act(async () => checkButton().click())
    owner = 'new'
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', employee_username: 'new-admin' } })))
    assert.equal(oldSignal.aborted, true)
    assert.match(document.querySelector('.long-leave-pending-card').textContent, /new/)
    await act(async () => wait.resolve(response(checked('STALE PRIVATE RESULT'))))
    assert.ok(!document.body.textContent.includes('STALE PRIVATE RESULT'))
    assert.equal(checkButton().disabled, false)
    assert.equal(document.querySelector('[aria-label="Kết quả kiểm tra old"]'), null)
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('account switching also discards old pending records and late error feedback', async () => {
  const original = globalThis.fetch, oldPending = deferred(), oldOverview = deferred(), root = createRoot(document.querySelector('#root'))
  let owner = 'old'; const signals = []
  globalThis.fetch = async (url, options) => {
    if (owner === 'old') { signals.push(options.signal); return url.endsWith('/pending') ? oldPending.promise : oldOverview.promise }
    return response(url.endsWith('/pending') ? { requests: [pendingRow('new')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'old' } })))
    owner = 'new'
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'new' } })))
    assert.ok(signals.every(signal => signal.aborted))
    await act(async () => { oldPending.resolve(response({ requests: [pendingRow('STALE PRIVATE RECORD')] })); oldOverview.resolve(response({ detail: 'STALE ERROR' }, 500)) })
    assert.ok(!document.body.textContent.includes('STALE'))
    assert.match(document.querySelector('.long-leave-pending-card').textContent, /new/)
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('removing admin access clears the panel and cancels in-flight checks without another read', async () => {
  const original = globalThis.fetch, wait = deferred(), root = createRoot(document.querySelector('#root'))
  let signal; const calls = []
  globalThis.fetch = async (url, options) => {
    calls.push(url)
    if (url.includes('/requests/')) { signal = options.signal; return wait.promise }
    return response(url.endsWith('/pending') ? { requests: [pendingRow('target')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', employee_username: 'same' } })))
    await act(async () => checkButton().click())
    const count = calls.length
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'letan', employee_username: 'same' } })))
    assert.equal(signal.aborted, true)
    assert.equal(document.querySelector('.long-leave-admin-panel'), null)
    await act(async () => wait.resolve(response({ detail: 'STALE ERROR' }, 500)))
    assert.equal(calls.length, count)
    assert.ok(!document.body.textContent.includes('STALE'))
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('confirmed decision cannot start under a switched account after delayed session retrieval', async () => {
  const original = globalThis.fetch, session = deferred(), root = createRoot(document.querySelector('#root'))
  const calls = []
  let sessionRequested = false
  globalThis.fetch = async (url, options) => {
    calls.push([url, options.method || 'GET'])
    return response(url.endsWith('/pending') ? { requests: [pendingRow('target')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'old' } })))
    await act(async () => [...document.querySelectorAll('.long-leave-decision-row button')].find(button => button.textContent.includes('Duyệt đơn')).click())
    globalThis.__annualGetSession = () => { sessionRequested = true; return session.promise }
    await act(async () => [...document.querySelectorAll('.system-dialog-confirm button')].find(button => button.textContent === 'Xác nhận').click())
    assert.equal(sessionRequested, true)
    delete globalThis.__annualGetSession
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'new' } })))
    await act(async () => session.resolve({ access_token: 'new-account-session' }))
    assert.ok(calls.every(([, method]) => method === 'GET'))
    assert.equal(document.querySelector('.system-dialog-error'), null)
  } finally { delete globalThis.__annualGetSession; await act(() => root.unmount()); globalThis.fetch = original }
})

const modal = () => document.querySelector('.system-dialog')
const closeModal = async () => { await act(async () => modal().querySelector('.primary-button').click()) }
const decisionButton = label => [...document.querySelectorAll('.long-leave-decision-row button')].find(node => node.textContent.includes(label))

// All API calls in these mounted flows are isolated fixtures; no business data
// or notification-read state is touched.
test('empty overlap is an explicit modal, Close/Escape preserve the card and the check can reopen', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), calls = []
  globalThis.fetch = async (url, options) => {
    calls.push([url, options.method || 'GET'])
    return response(url.includes('/requests/') ? { ...checked(), employee_count: 0, peak_with_applicant: 1, requests: [] }
      : url.endsWith('/pending') ? { requests: [pendingRow('empty')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'empty' } })))
    assert.equal(modal(), null, 'normal dashboard state does not open a notice')
    const opener = checkButton(); opener.focus()
    await act(async () => opener.click())
    assert.match(modal().textContent, /Không có nhân viên khác nghỉ trùng/)
    assert.equal(modal().querySelector('button').textContent, 'Đóng')
    assert.equal(document.body.style.overflow, 'hidden')
    assert.ok(!document.querySelector('.long-leave-pending-card').textContent.includes('Không có nhân viên khác'))
    await closeModal()
    assert.equal(document.activeElement, opener)
    assert.equal(document.body.style.overflow, '')
    await act(async () => opener.click())
    assert.ok(modal())
    await act(async () => document.activeElement.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    assert.equal(modal(), null)
    assert.ok(document.querySelector('.long-leave-pending-card'))
    assert.ok(calls.every(([, method]) => method === 'GET'))
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('overview check reports all results in a modal and rapid clicks issue one read', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), wait = deferred()
  let checks = 0
  globalThis.fetch = async url => {
    if (url.endsWith('/pending')) return response({ requests: [] })
    checks++
    return checks === 1 ? response({ days: [] }) : wait.promise
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
    const button = [...document.querySelectorAll('.leave-overlap-controls button')].find(node => node.textContent === 'Kiểm tra')
    await act(async () => { button.click(); button.click() })
    assert.equal(checks, 2)
    assert.equal(button.disabled, true)
    await act(async () => wait.resolve(response({ has_alert: true, days: [{ date: '2026-12-01', leave_count: 3, pending_count: 2, departments: [{ department_id: 'nhanvien', leave_count: 3, headcount: 4, exceeds_threshold: true }] }] })))
    assert.match(modal().textContent, /Có ngày từ 3 người nghỉ/)
    assert.match(modal().textContent, /01-12-2026: 3 người nghỉ/)
    assert.match(modal().textContent, /nhanvien: 3\/4 \(vượt ngưỡng\)/)
    await closeModal()
    assert.equal(button.disabled, false)
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('validation and approve/reject outcomes use scoped modals without changing confirmation choices', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), writes = []
  globalThis.fetch = async (url, options) => {
    if (options.method === 'POST') { writes.push(JSON.parse(options.body)); return response({ message: 'Đã duyệt đơn.', annual_leave_rows_created: 7 }) }
    return response(url.endsWith('/pending') ? { requests: [pendingRow('decision')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
    await act(async () => { decisionButton('Không duyệt').click(); decisionButton('Không duyệt').click() })
    assert.equal(document.querySelectorAll('.system-dialog').length, 1)
    assert.match(modal().textContent, /Vui lòng nhập lý do/)
    await closeModal()
    const input = document.querySelector('.long-leave-decision-row input')
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, 'Không đủ nhân sự')
      input.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    await act(async () => decisionButton('Không duyệt').click())
    assert.equal(modal().dataset.systemDialog, 'confirm')
    assert.equal(document.activeElement.textContent, 'Hủy')
    await act(async () => document.activeElement.dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    assert.equal(writes.length, 0)
    assert.equal(input.value, 'Không đủ nhân sự')
    await act(async () => { decisionButton('Duyệt đơn').click(); decisionButton('Duyệt đơn').click() })
    assert.equal(document.querySelectorAll('.system-dialog-confirm').length, 1)
    await closeModal()
    assert.deepEqual(writes, [{ decision: 'approve', rejection_reason: '' }])
    assert.equal(modal().dataset.systemDialog, 'success')
    assert.match(modal().textContent, /Đã tạo 7 ngày Phép năm/)
    await closeModal()
    assert.equal(modal(), null)
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('network/HTTP failures queue without overwriting and account removal clears visible and queued feedback', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root'))
  globalThis.fetch = async url => {
    if (url.endsWith('/pending')) throw new Error('Mất kết nối danh sách đơn')
    return response({ detail: 'Không tải được tổng quan' }, 503)
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'old' } })))
    assert.equal(document.querySelectorAll('.system-dialog').length, 1)
    const first = modal().textContent
    await closeModal()
    assert.ok(modal())
    assert.notEqual(modal().textContent, first)
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'letan', id: 'old' } })))
    assert.equal(modal(), null)
    assert.equal(document.body.style.overflow, '')
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('long result lists retain text safely and browser Back closes feedback without changing data', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), writes = []
  globalThis.fetch = async (url, options) => {
    if (options.method) writes.push(options.method)
    return response(url.includes('/requests/') ? { ...checked(), employee_count: 80, requests: Array.from({ length: 80 }, (_, i) => ({ ...checked().requests[0], id: `${i}`, employee_name: `Employee ${i} <img src=x>` })) }
      : url.endsWith('/pending') ? { requests: [pendingRow('long')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
    await act(async () => checkButton().click())
    assert.match(modal().textContent, /Employee 79 <img src=x>/)
    assert.equal(modal().querySelector('img'), null)
    await act(async () => window.dispatchEvent(new window.PopStateEvent('popstate')))
    assert.equal(modal(), null)
    assert.equal(document.body.style.overflow, '')
    assert.ok(document.querySelector('.long-leave-pending-card'))
    assert.deepEqual(writes, [])
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('partial date drafts show scoped validation and never check the previous committed range', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), calls = []
  globalThis.fetch = async url => { calls.push(url); return response(url.endsWith('/pending') ? { requests: [] } : { days: [] }) }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin', id: 'draft' } })))
    const input = document.querySelector('.leave-overlap-controls input[type="text"]')
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, '12')
      input.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    const before = calls.length
    await act(async () => [...document.querySelectorAll('.leave-overlap-controls button')].find(node => node.textContent === 'Kiểm tra').click())
    assert.equal(calls.length, before)
    assert.equal(modal().dataset.systemDialog, 'warning')
    assert.match(modal().textContent, /dd-mm-yyyy/)
    await closeModal()
    assert.equal(input.value, '12')
    assert.equal(document.activeElement, input)
    await act(async () => [...document.querySelectorAll('.leave-overlap-controls button')].find(node => node.textContent === 'Kiểm tra').click())
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'letan', id: 'draft' } })))
    assert.equal(modal(), null)
    assert.equal(document.body.style.overflow, '')
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('HTTP decision failures preserve the rejection draft and never report success', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), writes = []
  globalThis.fetch = async (url, options) => {
    if (options.method === 'POST') { writes.push(JSON.parse(options.body)); return response({ detail: 'Đơn đã thay đổi. Vui lòng tải lại.' }, 409) }
    return response(url.endsWith('/pending') ? { requests: [pendingRow('conflict')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
    const input = document.querySelector('.long-leave-decision-row input')
    await act(async () => {
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, 'Chưa phù hợp')
      input.dispatchEvent(new window.Event('input', { bubbles: true }))
    })
    await act(async () => decisionButton('Không duyệt').click())
    await closeModal()
    assert.deepEqual(writes, [{ decision: 'reject', rejection_reason: 'Chưa phù hợp' }])
    assert.equal(modal().dataset.systemDialog, 'error')
    assert.match(modal().textContent, /Đơn đã thay đổi/)
    await closeModal()
    assert.equal(input.value, 'Chưa phù hợp')
    assert.equal(decisionButton('Không duyệt').disabled, false)
    assert.equal(document.querySelector('.system-dialog-success'), null)
  } finally { await act(() => root.unmount()); globalThis.fetch = original }
})

test('existing feedback categories route once while new check results and decisions do not add routing', async () => {
  const original = globalThis.fetch, root = createRoot(document.querySelector('#root')), categories = []
  const capture = event => categories.push(event.detail.category)
  window.addEventListener('vera-system-feedback', capture)
  let checkFails = true
  globalThis.fetch = async (url, options) => {
    if (url.includes('/overlap') && url.includes('/requests/')) return checkFails ? response({ detail: 'Không kiểm tra được đơn.' }, 500) : response(checked())
    if (options.method === 'POST') return response({ message: 'Đã duyệt đơn.' })
    return response(url.endsWith('/pending') ? { requests: [pendingRow('routing')] } : { days: [] })
  }
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
    await act(async () => { decisionButton('Không duyệt').click(); decisionButton('Không duyệt').click() })
    assert.deepEqual(categories, ['ui_guidance'])
    await closeModal()
    await act(async () => checkButton().click())
    assert.deepEqual(categories, ['ui_guidance', 'ui_error'])
    await closeModal(); checkFails = false
    await act(async () => checkButton().click())
    assert.equal(categories.length, 2)
    await closeModal()
    await act(async () => decisionButton('Duyệt đơn').click())
    assert.equal(categories.length, 2)
    await closeModal()
    assert.deepEqual(categories, ['ui_guidance', 'ui_error', 'ui_success'])
    await closeModal()
  } finally { window.removeEventListener('vera-system-feedback', capture); await act(() => root.unmount()); globalThis.fetch = original }
})
