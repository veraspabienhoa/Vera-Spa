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
    const result=card.querySelector('[aria-label="Kết quả kiểm tra november"]')
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
    assert.match(document.querySelector('[role="alert"]').textContent, /Khoảng ngày/)
    assert.equal(checkButton().disabled, false)
    await act(async () => checkButton().click())
    assert.equal(checks, 2)
    assert.ok(!document.querySelector('[role="alert"]'))
    assert.match(document.querySelector('[aria-label="Kết quả kiểm tra target"]').textContent, /Other/)
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
    assert.equal(document.querySelector('[role="alert"]'), null)
  } finally { delete globalThis.__annualGetSession; await act(() => root.unmount()); globalThis.fetch = original }
})
