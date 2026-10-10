import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { JSDOM } from 'jsdom'
import { answerDialogs } from './dialogAnswers.mjs'

const NativeDate = globalThis.Date
const now = NativeDate.parse('2026-10-07T05:00:00Z')
globalThis.Date = class extends NativeDate {
  constructor(...args) { super(...(args.length ? args : [now])) }
  static now() { return now }
}
after(() => { globalThis.Date = NativeDate })
const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/WorkSchedulePage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'lucide-react'], loader: { '.css': 'empty' },
  define: { 'import.meta.env.VITE_VERA_API_BASE_URL': '"https://vera.test"' },
  plugins: [{ name: 'fixture-boundaries', setup(b) {
    b.onResolve({ filter: /\/lib\/(api|supabase)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onResolve({ filter: /\/components\/ScheduleViolations$/ }, () => ({ path: 'violations', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: {
      api: 'export const apiRequest = (...args)=>globalThis.__scheduleRequest(...args); export const veraApi = {};',
      supabase: 'export const getCurrentSession = async()=>null;',
      violations: 'export default function ScheduleViolations(){return null}',
    }[path], loader: 'js' }))
  } }],
})
const deferred = () => { let resolve, reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no }); return { promise, resolve, reject } }
const day = '2026-10-05'
const row = (employee_username, shift_code = 'Ca 1', revision = 1, department = 'locker', work_date = day) => ({ employee_username, work_date, department, shift_code, revision })

async function fixture(initial = [row('A'), row('B'), row('C')]) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true, url: 'https://vera.test' })
  dom.window.confirm = () => false
  const stopDialogs = answerDialogs(dom.window)
  const globals = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', '__scheduleRequest', 'fetch']
  const descriptors = Object.fromEntries(globals.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const control = { rows: initial, readHook: null, writeHook: null, writes: [], reads: [], importRows: [] }
  let revision = 100
  const key = r => `${r.department || 'locker'}|${r.employee_username}|${r.work_date}`
  const timers = new Map()
  const realSetTimeout = dom.window.setTimeout.bind(dom.window), realClearTimeout = dom.window.clearTimeout.bind(dom.window)
  let timerId = 1000000
  dom.window.setTimeout = (fn, delay, ...args) => { if (delay !== 900) return realSetTimeout(fn, delay, ...args); const id = ++timerId; timers.set(id, () => fn(...args)); return id }
  dom.window.clearTimeout = id => { timers.delete(id); realClearTimeout(id) }
  const commit = payload => {
    const conflicts = [...payload.rows, ...payload.deletes].filter(change => {
      const before = control.rows.find(r => key(r) === key(change))
      return (before?.revision || 0) !== change.expected_revision
    })
    if (conflicts.length) throw Object.assign(Error('Lịch đã thay đổi'), { status: 409, payload: { detail: { code: 'schedule_conflict', conflicts } } })
    const revisions = []
    for (const change of payload.rows) {
      const next = { ...change, revision: ++revision }
      control.rows = [...control.rows.filter(r => key(r) !== key(change)), next]
      revisions.push(next)
    }
    for (const change of payload.deletes) control.rows = control.rows.filter(r => key(r) !== key(change))
    return { ok: true, saved: payload.rows.length, deleted: payload.deletes.length, revisions }
  }
  const request = async (path, options = {}) => {
    if (path.includes('/violations') || path.includes('/combo-sales')) return { rows: [] }
    if (options.method === 'PUT') {
      const payload = JSON.parse(options.body)
      control.writes.push(payload)
      return control.writeHook ? control.writeHook(payload, commit) : commit(payload)
    }
    assert.equal(options.method || 'GET', 'GET', 'schedule changes must use one atomic PUT, never legacy DELETE')
    const params = new URL(path, 'https://vera.test').searchParams
    control.reads.push({ path, params, options })
    const read = () => ({ rows: control.rows.filter(r => r.department === params.get('department') && r.work_date >= params.get('start') && r.work_date <= params.get('end')),
      employees: ['A', 'B', 'C'].map(username => ({ username, system_name: username })),
      shift_definitions: { locker: { 'Ca 1': { start: '08:00', end: '16:00' }, 'Ca 2': { start: '16:00', end: '23:00' } }, tapvu: { 'Ca 1': {}, 'Ca 2': {} } },
    })
    return control.readHook ? control.readHook(params, read, options) : read()
  }
  Object.defineProperties(globalThis, {
    window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
    navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
    __scheduleRequest: { value: request, configurable: true }, fetch: { value: async () => ({ ok: true, json: async () => ({ rows: control.importRows }) }), configurable: true },
  })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(dom.window.document.querySelector('#root'))
  await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'admin' } })))
  const button = text => [...dom.window.document.querySelectorAll('button')].find(node => node.textContent.trim() === text)
  const editor = (name, index = 0) => [...dom.window.document.querySelectorAll('.schedule-grid tbody tr')].find(tr => tr.querySelector('strong')?.textContent === name)?.querySelectorAll('select.shift-select')[index]
  return { ...control, control, dom, button, editor,
    edit: async (name, value, index = 0) => { const node = editor(name, index); assert.ok(node); assert.equal(node.disabled, false); await act(() => { node.value = value; node.dispatchEvent(new dom.window.Event('change', { bubbles: true })) }) },
    click: async text => { const node = button(text); assert.ok(node, text); assert.equal(node.disabled, false, text); await act(async () => node.click()) },
    autosave: async () => { const jobs = [...timers.values()]; timers.clear(); await act(async () => { for (const job of jobs) job() }) },
    dispose: async () => { await act(() => root.unmount()); stopDialogs(); dom.window.close(); for (const [key, descriptor] of Object.entries(descriptors)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] } },
  }
}

test('one atomic save sends only edited cells and their baselines, including deletes and absent cells', async () => {
  const f = await fixture([row('A', 'Ca 1', 7), row('B', 'Ca 2', 9)])
  try {
    await f.edit('A', '')
    await f.edit('B', 'Nghỉ')
    await f.edit('C', 'Ca 2')
    await f.click('Lưu lịch')
    assert.equal(f.control.writes.length, 1)
    const payload = f.control.writes[0]
    assert.deepEqual(payload.deletes, [{ work_date: day, employee_username: 'A', expected_revision: 7 }])
    assert.deepEqual(payload.rows.map(r => [r.employee_username, r.expected_revision]), [['B', 9], ['C', 0]])
    assert.equal(f.button('Lưu lịch').disabled, true)
  } finally { await f.dispose() }
})

test('409 refresh retains disjoint drafts, shows remote changes and requires review before retry', async () => {
  const f = await fixture()
  try {
    await f.edit('A', 'Ca 2')
    await f.edit('B', 'Ca 2')
    f.control.rows = [row('A', 'Nghỉ', 8), row('B'), row('C', 'Ca 2', 10)]
    await f.click('Lưu lịch')
    assert.equal(f.editor('A').value, 'Ca 2')
    assert.equal(f.editor('B').value, 'Ca 2')
    assert.equal(f.editor('C').value, 'Ca 2')
    assert.match(f.dom.window.document.querySelector('.schedule-conflicts').textContent, /Trên máy chủ: Nghỉ/)
    assert.match(f.dom.window.document.querySelector('.schedule-conflicts').textContent, /05-10-2026/)
    assert.equal(f.button('Lưu lịch').disabled, true)
    await f.autosave()
    assert.equal(f.control.writes.length, 1)
    await f.click('Dùng lịch trên máy chủ')
    assert.equal(f.editor('A').value, 'Nghỉ')
    await f.autosave()
    assert.equal(f.control.writes.length, 1)
    await f.click('Lưu lịch')
    assert.deepEqual(f.control.writes[1].rows.map(r => [r.employee_username, r.expected_revision]), [['B', 1]])
  } finally { await f.dispose() }
})

test('stale delete needs explicit confirmation to reapply against the refreshed revision', async () => {
  const f = await fixture()
  try {
    await f.edit('A', '')
    f.control.rows[0] = row('A', 'Ca 2', 17)
    await f.click('Lưu lịch')
    assert.match(f.dom.window.document.querySelector('.schedule-conflicts').textContent, /Trống \(xóa lịch\)/)
    await f.click('Áp dụng lại bản sửa của tôi')
    assert.ok(f.dom.window.document.querySelector('.schedule-conflicts'), 'cancel must leave the conflict unresolved')
    assert.equal(f.control.writes.length, 1)
    f.dom.window.confirm = () => true
    await f.click('Áp dụng lại bản sửa của tôi')
    assert.equal(f.dom.window.document.querySelector('.schedule-conflicts'), null)
    await f.autosave()
    assert.equal(f.control.writes.length, 1)
    await f.click('Lưu lịch')
    assert.equal(f.control.writes[1].deletes[0].expected_revision, 17)
  } finally { await f.dispose() }
})

test('slow save and repeated clicks keep newer same-cell and disjoint edits pending', async () => {
  const f = await fixture()
  const wait = deferred()
  try {
    f.control.writeHook = async (payload, commit) => { await wait.promise; return commit(payload) }
    await f.edit('A', 'Ca 2')
    await f.click('Lưu lịch')
    await act(() => f.button('Lưu lịch').click())
    await f.edit('A', 'Nghỉ')
    await f.edit('B', 'Ca 2')
    assert.equal(f.control.writes.length, 1)
    await act(async () => wait.resolve())
    assert.equal(f.editor('A').value, 'Nghỉ')
    assert.equal(f.editor('B').value, 'Ca 2')
    assert.equal(f.button('Lưu lịch').disabled, false)
    await f.click('Lưu lịch')
    assert.deepEqual(f.control.writes[1].rows.map(r => [r.employee_username, r.shift_code, r.expected_revision]), [['A', 'Nghỉ', 101], ['B', 'Ca 2', 1]])
  } finally { wait.resolve(); await f.dispose() }
})

test('network failure blocks blind retry; refresh preserves drafts and detects an already committed save', async () => {
  const f = await fixture()
  try {
    f.control.writeHook = (payload, commit) => { commit(payload); throw Error('Mất kết nối') }
    await f.edit('A', 'Ca 2')
    await f.click('Lưu lịch')
    assert.equal(f.editor('A').value, 'Ca 2')
    assert.equal(f.button('Lưu lịch').disabled, true)
    await f.autosave()
    assert.equal(f.control.writes.length, 1)
    await f.click('Tải lại để đối chiếu')
    assert.equal(f.editor('A').value, 'Ca 2')
    assert.equal(f.button('Lưu lịch').disabled, true)
    assert.equal(f.dom.window.document.querySelector('.schedule-recovery'), null)
    assert.equal(f.dom.window.document.querySelector('.schedule-conflicts'), null)
    assert.equal(f.control.writes.length, 1)
  } finally { await f.dispose() }
})

test('failed conflict refresh retains edits and must recover before resolving or saving', async () => {
  const f = await fixture()
  try {
    await f.edit('A', '')
    await f.edit('B', 'Ca 2')
    f.control.rows[0] = row('A', 'Nghỉ', 12)
    f.control.readHook = () => { throw Error('Mất mạng') }
    await f.click('Lưu lịch')
    assert.equal(f.editor('A').value, '')
    assert.equal(f.editor('B').value, 'Ca 2')
    assert.equal(f.button('Lưu lịch').disabled, true)
    await f.autosave()
    assert.equal(f.control.writes.length, 1)
    f.control.readHook = null
    await f.click('Tải lại để đối chiếu')
    assert.ok(f.dom.window.document.querySelector('.schedule-conflicts'))
    assert.equal(f.editor('B').value, 'Ca 2')
  } finally { await f.dispose() }
})

test('late reads after navigation cannot overwrite the new scope, even if abort is ignored', async () => {
  const f = await fixture([row('A'), row('A', 'Nghỉ', 50, 'tapvu')])
  const wait = deferred()
  try {
    f.control.readHook = (params, read) => params.get('department') === 'locker' && params.get('start') === '2026-10-12' ? wait.promise : read()
    await f.click('Tuần sau')
    await f.click('Tạp vụ')
    await f.click('Tuần này')
    assert.equal(f.editor('A').value, 'Nghỉ')
    await act(async () => wait.resolve({ rows: [row('A', 'Ca 2', 80)], employees: [{ username: 'A' }], shift_definitions: {} }))
    assert.equal(f.editor('A').value, 'Nghỉ')
    assert.equal(f.dom.window.document.querySelector('.schedule-department-tabs button.active').textContent, 'Tạp vụ')
  } finally { wait.resolve({ rows: [] }); await f.dispose() }
})

test('late save does not replace another view and a revisit loads after the save settles', async () => {
  const f = await fixture([row('A'), row('A', 'Nghỉ', 50, 'tapvu')])
  const wait = deferred()
  try {
    f.control.writeHook = async (payload, commit) => { await wait.promise; return commit(payload) }
    await f.edit('A', 'Ca 2')
    await f.click('Lưu lịch')
    await f.edit('A', 'Nghỉ')
    await f.click('Tạp vụ')
    assert.equal(f.editor('A').value, 'Nghỉ')
    await act(async () => wait.resolve())
    assert.equal(f.editor('A').value, 'Nghỉ')
    assert.doesNotMatch(f.dom.window.document.querySelector('.stable-feedback').textContent, /Đã lưu/)
    await f.click('Locker')
    assert.equal(f.editor('A').value, 'Nghỉ', 'newer local draft survives navigation and acknowledgement')
    await f.click('Lưu lịch')
    assert.equal(f.control.writes[1].rows[0].expected_revision, 101)
  } finally { wait.resolve(); await f.dispose() }
})

test('Excel preview retains each target baseline and waits for manual save', async () => {
  const f = await fixture([row('A', 'Ca 1', 7)])
  try {
    f.control.importRows = [row('A', 'Ca 2', 999), row('B', 'Nghỉ', 999)]
    const input = f.dom.window.document.querySelector('input[type="file"]')
    Object.defineProperty(input, 'files', { value: [new f.dom.window.File(['preview'], 'schedule.xlsx')] })
    await act(async () => input.dispatchEvent(new f.dom.window.Event('change', { bubbles: true })))
    assert.equal(f.editor('A').value, 'Ca 2')
    assert.equal(f.editor('B').value, 'Nghỉ')
    await f.autosave()
    assert.equal(f.control.writes.length, 0)
    await f.click('Lưu lịch')
    assert.deepEqual(f.control.writes[0].rows.map(r => [r.employee_username, r.expected_revision]), [['A', 7], ['B', 0]])
  } finally { await f.dispose() }
})

test('Excel arriving during a slow save preserves its newer manual-save boundary after acknowledgement', async () => {
  const f = await fixture([row('A', 'Ca 1', 7), row('B', 'Ca 1', 8)])
  const wait = deferred()
  try {
    f.control.writeHook = async (payload, commit) => { await wait.promise; return commit(payload) }
    // The chooser was opened before saving, but file selection can arrive later.
    await f.click('Import Excel')
    await f.edit('A', 'Ca 2')
    await f.autosave()
    assert.equal(f.control.writes.length, 1)
    f.control.importRows = [row('A', 'Nghỉ', 999), row('B', 'Ca 2', 999)]
    const input = f.dom.window.document.querySelector('input[type="file"]')
    Object.defineProperty(input, 'files', { value: [new f.dom.window.File(['preview'], 'schedule.xlsx')] })
    await act(async () => input.dispatchEvent(new f.dom.window.Event('change', { bubbles: true })))
    assert.equal(f.editor('A').value, 'Nghỉ')
    await act(async () => wait.resolve())
    await f.autosave()
    assert.equal(f.control.writes.length, 1, 'an old acknowledgement must never release an imported draft for autosave')
    assert.match(f.dom.window.document.querySelector('.schedule-autosave-state').textContent, /Chờ kiểm tra và Lưu lịch/)
    await f.click('Lưu lịch')
    assert.deepEqual(f.control.writes[1].rows.map(r => [r.employee_username, r.shift_code, r.expected_revision]), [['A', 'Nghỉ', 101], ['B', 'Ca 2', 8]])
  } finally { wait.resolve(); await f.dispose() }
})

test('returning to a scope while its save is pending postpones the read until that write settles', async () => {
  const f = await fixture([row('A'), row('A', 'Nghỉ', 50, 'tapvu')])
  const wait = deferred()
  try {
    f.control.writeHook = async (payload, commit) => { await wait.promise; return commit(payload) }
    await f.edit('A', 'Ca 2')
    await f.click('Lưu lịch')
    await f.click('Tạp vụ')
    const reads = f.control.reads.length
    await f.click('Locker')
    assert.equal(f.control.reads.length, reads, 'GET must not race ahead of the still-running PUT')
    assert.equal(f.editor('A').disabled, true)
    await act(async () => wait.resolve())
    assert.ok(f.control.reads.length > reads)
    assert.equal(f.editor('A').value, 'Ca 2')
    assert.equal(f.editor('A').disabled, false)
    assert.equal(f.button('Lưu lịch').disabled, true)
  } finally { wait.resolve(); await f.dispose() }
})

test('paste copies only values and uses the target cell revision', async () => {
  const f = await fixture([row('A', 'Ca 2', 6), row('B', 'Ca 1', 19)])
  try {
    const source = f.editor('A').closest('td'), target = f.editor('B').closest('td')
    await act(async () => source.dispatchEvent(new f.dom.window.KeyboardEvent('keydown', { key: 'c', ctrlKey: true, bubbles: true })))
    await act(async () => target.dispatchEvent(new f.dom.window.KeyboardEvent('keydown', { key: 'v', ctrlKey: true, bubbles: true })))
    assert.equal(f.editor('B').value, 'Ca 2')
    await f.click('Lưu lịch')
    assert.deepEqual(f.control.writes[0].rows.map(r => [r.employee_username, r.expected_revision]), [['B', 19]])
  } finally { await f.dispose() }
})

test('blank Excel cells with leftover metadata cannot trigger recurring empty writes', async () => {
  const f = await fixture([])
  try {
    f.control.importRows = [{ ...row('A', ''), note: 'left over', start_time: '09:00', overtime_shift: 'TC Ca 1' }]
    const input = f.dom.window.document.querySelector('input[type="file"]')
    Object.defineProperty(input, 'files', { value: [new f.dom.window.File(['preview'], 'schedule.xlsx')] })
    await act(async () => input.dispatchEvent(new f.dom.window.Event('change', { bubbles: true })))
    assert.equal(f.button('Lưu lịch').disabled, true)
    await f.autosave()
    await f.autosave()
    assert.equal(f.control.writes.length, 0)
  } finally { await f.dispose() }
})
