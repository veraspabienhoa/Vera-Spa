import assert from 'node:assert/strict'
import test from 'node:test'
import { readFileSync } from 'node:fs'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { attendanceSummary, deadlineMsFor, matchesAttendanceSummary } from '../src/lib/attendanceSummary.js'

const now = Date.parse('2026-10-11T18:00:00+07:00')
const base = { date: '11/10/2026', shift: 'Ca 1', break_enabled: true, break_department: 'Locker', check_in: '10:00:00' }
const records = [
  { ...base, employee_name: 'Complete', break_out: '15:00:00', break_in: '16:00:00' },
  { ...base, employee_name: 'Complete late', break_out: '15:00:00', break_in: '17:00:00', break_return_late_minutes: 30 },
  { ...base, employee_name: 'Open future', break_out: '17:00:00', break_return_deadline_iso: '2026-10-11T18:30:00' },
  { ...base, employee_name: 'Open overdue', break_out: '15:00:00', break_return_deadline: '16:30:00' },
  { ...base, employee_name: 'Not started' },
  { ...base, employee_name: 'Restricted outside', break_restricted_reason: 'registered leave', break_out: '15:00:00' },
  { ...base, employee_name: 'Restricted inside', break_restricted_reason: 'registered leave' },
  { ...base, employee_name: 'Disabled', break_enabled: false },
].map((item, index) => ({ ...item, employee_code: `TEST${index}` }))
const namesFor = filter => records.filter(item => matchesAttendanceSummary(item, filter, now)).map(item => item.employee_name)

test('cards preserve existing overlapping classifications without changing records', () => {
  const original = JSON.stringify(records)
  assert.deepEqual(attendanceSummary(records, now), { all: 8, breaks: 2, over: 3, incomplete: 3 })
  assert.deepEqual(namesFor('breaks'), ['Complete', 'Complete late'])
  assert.deepEqual(namesFor('over'), ['Complete late', 'Open overdue', 'Restricted outside'])
  assert.deepEqual(namesFor('incomplete'), ['Open future', 'Open overdue', 'Not started'])
  assert.equal(namesFor('all').length, 8)
  assert.deepEqual(namesFor('unknown'), [])
  assert.equal(JSON.stringify(records), original)
  assert.deepEqual(attendanceSummary([], now), { all: 0, breaks: 0, over: 0, incomplete: 0 })
})

test('Vietnam deadlines preserve offsets, naive ISO, date formats and strict boundary', () => {
  for (const stamp of ['2026-10-11T18:00:00+07:00', '2026-10-11T11:00:00Z', '2026-10-11T18:00:00', '2026-10-11 18:00:00']) assert.equal(deadlineMsFor({ break_return_deadline_iso: stamp }), now)
  for (const date of ['11/10/2026', '11-10-2026', '2026-10-11']) {
    const row = { ...base, date, break_out: '16:30:00', break_return_deadline: '18:00:00' }
    assert.equal(deadlineMsFor(row), now)
    assert.equal(matchesAttendanceSummary(row, 'over', now), false)
    assert.equal(matchesAttendanceSummary(row, 'over', now + 1), true)
  }
  assert.equal(deadlineMsFor({ ...base, break_return_deadline: '18:00:00.500' }), now + 500)
  assert.equal(deadlineMsFor({ ...base, break_return_deadline_iso: 'invalid', break_return_deadline: '18:00' }), now)
  for (const row of [{}, { ...base, break_return_deadline: '24:00:00' }, { ...base, break_return_deadline: '18:60:00' }, { date: '31/02/2026', break_return_deadline: '18:00:00' }, { break_return_deadline_iso: '2026-02-31T18:00:00' }]) assert.ok(Number.isNaN(deadlineMsFor(row)))
})

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Page from './src/pages/SnapshotPage';window.act=act;window.root=createRoot(document.getElementById('root'));window.mount=user=>window.root.render(<Page user={user}/>);`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' },
  define: { 'import.meta.env': JSON.stringify({ VITE_VERA_API_BASE_URL: 'https://api.test' }) },
  plugins: [{ name: 'auth-fixture', setup(b) {
    b.onResolve({ filter: /\/lib\/supabase$/ }, args => ({ path: args.path, namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export const getCurrentSession=async()=>({access_token:window.sessionToken});' }))
  } }],
})
const user = { id: 'one', username: 'tester', role: 'letan', permissions: { snapshot_today: true, snapshot_export: true } }
const response = rows => ({ ok: true, json: async () => ({ records: rows, filters: { employees: [], departments: [], shifts: [] } }) })
async function setup(fetchOverride) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window, calls = []
  w.Headers = Headers; w.IS_REACT_ACT_ENVIRONMENT = true; w.sessionToken = 'account-one'; w.now = now
  w.Date.now = () => w.now
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  const intervals = new Map(); let intervalId = 0
  w.setInterval = callback => { intervals.set(++intervalId, callback); return intervalId }
  w.clearInterval = id => intervals.delete(id)
  w.URL.createObjectURL = () => 'blob:test'; w.URL.revokeObjectURL = () => {}
  w.HTMLAnchorElement.prototype.click = function () { w.downloaded = this.download }
  w.fetch = async (url, options = {}) => {
    const u = new URL(url); calls.push({ url: u, options })
    if (fetchOverride) { const result = fetchOverride(u, options); if (result !== undefined) return result }
    if (u.pathname.endsWith('.xlsx')) return { ok: true, blob: async () => new w.Blob(['xlsx']), headers: new Headers() }
    return response(records.filter(item => ['employee', 'department', 'shift'].every(key => {
      const value = u.searchParams.get(key)
      return !value || item[{ employee: 'employee_name', department: 'break_department', shift: 'shift' }[key]].includes(value)
    })))
  }
  w.eval(built.outputFiles[0].text)
  await w.act(async () => w.mount(user))
  const cards = () => [...w.document.querySelectorAll('.attendance-kpi')]
  const rows = () => [...w.document.querySelectorAll('tbody tr')].map(row => row.children[1].querySelector('strong').textContent)
  const click = index => w.act(async () => cards()[index].click())
  const type = (node, value) => w.act(async () => {
    Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, 'value').set.call(node, value)
    node.dispatchEvent(new w.Event('input', { bubbles: true }))
  })
  const flush = () => w.act(async () => new Promise(resolve => setTimeout(resolve, 280)))
  const button = label => [...w.document.querySelectorAll('button')].find(node => node.textContent.trim() === label)
  const cleanup = async () => { await w.act(async () => w.root.unmount()); w.close() }
  return { w, calls, cards, rows, click, type, flush, button, cleanup, intervals }
}

test('all four native buttons filter, remain focused, and keep all card totals stable', async () => {
  const h = await setup()
  try {
    const count = h.calls.length
    const expected = [namesFor('all'), namesFor('breaks'), namesFor('over'), namesFor('incomplete')]
    for (const index of [1, 2, 3, 0]) {
      const card = h.cards()[index]
      assert.equal(card.tagName, 'BUTTON'); assert.equal(card.type, 'button')
      assert.ok(h.w.document.getElementById(card.getAttribute('aria-controls')))
      card.focus(); await h.click(index)
      assert.equal(h.w.document.activeElement, card)
      assert.deepEqual([...h.rows()].sort(), [...expected[index]].sort())
      assert.equal(card.getAttribute('aria-pressed'), 'true')
      assert.equal(h.cards().filter(node => node.getAttribute('aria-pressed') === 'true').length, 1)
      assert.deepEqual(h.cards().map(node => node.querySelector('strong').textContent), ['8', '2', '3', '3'])
    }
    assert.equal(h.calls.length, count, 'card clicks never start snapshot/device reads')
    assert.match(h.w.document.querySelector('.panel-title-row p').textContent, /\d{2}-\d{2}-\d{4}/)
  } finally { await h.cleanup() }
})

test('rapid switches and repeat click use the latest selection; Bỏ lọc resets group', async () => {
  const h = await setup()
  try {
    await h.w.act(async () => { h.cards()[1].click(); h.cards()[2].click(); h.cards()[3].click() })
    assert.deepEqual([...h.rows()].sort(), namesFor('incomplete').sort())
    await h.click(3); assert.equal(h.rows().length, 8)
    await h.click(2)
    await h.w.act(async () => h.button('Bỏ lọc').click())
    assert.equal(h.rows().length, 8); assert.equal(h.cards()[0].getAttribute('aria-pressed'), 'true')
    assert.equal(h.button('Bỏ lọc'), undefined)
  } finally { await h.cleanup() }
})

test('card filter composes with name, department, shift and date; export uses same scope', async () => {
  const h = await setup()
  try {
    await h.click(2)
    for (const [placeholder, value] of [['Tìm tên nhân viên', 'Complete'], ['Tìm bộ phận', 'Locker'], ['Tìm ca làm việc', 'Ca 1']]) {
      await h.type(h.w.document.querySelector(`input[placeholder="${placeholder}"]`), value)
      assert.equal(h.button('Xuất excel').disabled, true)
      await h.flush()
    }
    await h.type(h.w.document.querySelector('input[aria-label="Ngày chấm công"]'), '11-10-2026')
    assert.deepEqual(h.rows(), ['Complete late'])
    assert.deepEqual(h.cards().map(node => node.querySelector('strong').textContent), ['2', '2', '1', '0'])
    await h.w.act(async () => h.button('Xuất excel').click())
    const exportUrl = h.calls.findLast(call => call.url.pathname.endsWith('.xlsx')).url
    assert.equal(exportUrl.pathname, '/v2/snapshot/export-summary.xlsx')
    const exported = exportUrl.searchParams
    assert.deepEqual(Object.fromEntries(exported), { start: '2026-10-11', end: '2026-10-11', employee: 'Complete', department: 'Locker', shift: 'Ca 1', summary_filter: 'over' })
    assert.equal(h.w.downloaded, 'VERA_ChamCong.xlsx')
    await h.click(3); assert.deepEqual(h.rows(), [])
    assert.match(h.w.document.querySelector('.setup-note').textContent, /Không có dữ liệu phù hợp/)
    await h.w.act(async () => h.button('Bỏ lọc').click())
    assert.equal(h.rows().length, 8)
    assert.equal(h.w.document.querySelector('input[aria-label="Ngày chấm công"]').value, '11-10-2026')
  } finally { await h.cleanup() }
})

test('live deadline updates overdue count and filtered rows without network activity', async () => {
  const h = await setup()
  try {
    await h.click(2); const calls = h.calls.length
    await h.w.act(async () => { h.w.now = Date.parse('2026-10-11T18:30:00.001+07:00'); for (const tick of h.intervals.values()) tick() })
    assert.equal(h.cards()[2].querySelector('strong').textContent, '4')
    assert.ok(h.rows().includes('Open future')); assert.equal(h.calls.length, calls)
  } finally { await h.cleanup() }
})

test('changed date clears old rows; slow response cannot overwrite current group', async () => {
  let releaseOld, oldSignal, releaseNew
  const h = await setup((url, options) => {
    if (url.searchParams.get('start') === '2026-10-07') {
      oldSignal = options.signal
      return new Promise(resolve => { releaseOld = () => resolve(response([{ ...records[0], employee_name: 'Old date' }])) })
    }
    if (url.searchParams.get('start') === '2026-10-08') return new Promise(resolve => { releaseNew = () => resolve(response([{ ...records[1], employee_name: 'New date' }])) })
  })
  try {
    const date = h.w.document.querySelector('input[aria-label="Ngày chấm công"]')
    await h.type(date, '07-10-2026'); assert.deepEqual(h.rows(), []); assert.equal(h.button('Xuất excel').disabled, true)
    await h.click(2); await h.type(date, '08-10-2026'); assert.equal(oldSignal.aborted, true)
    await h.w.act(async () => releaseNew()); assert.deepEqual(h.rows(), ['New date'])
    await h.w.act(async () => releaseOld()); assert.deepEqual(h.rows(), ['New date'])
    assert.equal(h.cards()[2].getAttribute('aria-pressed'), 'true')
  } finally { await h.cleanup() }
})

test('failed new query never enables export of an unrelated old result', async () => {
  const h = await setup(url => url.searchParams.get('start') === '2026-10-07' ? Promise.reject(new Error('test unavailable')) : undefined)
  try {
    await h.type(h.w.document.querySelector('input[aria-label="Ngày chấm công"]'), '07-10-2026')
    assert.deepEqual(h.rows(), []); assert.equal(h.button('Xuất excel').disabled, true)
    assert.match(h.w.document.querySelector('.error-box').textContent, /test unavailable/)
  } finally { await h.cleanup() }
})

test('account and permission changes reset selection and reject prior account response', async () => {
  let resolveFirst, firstSignal
  const h = await setup((url, options) => {
    if (options.headers.get('Authorization') === 'Bearer account-one') {
      firstSignal = options.signal
      return new Promise(resolve => { resolveFirst = () => resolve(response([{ ...records[0], employee_name: 'Private old account' }])) })
    }
    return response([])
  })
  try {
    await h.click(1); h.w.sessionToken = 'account-two'
    await h.w.act(async () => h.w.mount({ ...user, id: 'two', username: 'other', permissions: { snapshot_today: true } }))
    assert.equal(firstSignal.aborted, true); assert.equal(h.cards()[0].getAttribute('aria-pressed'), 'true')
    assert.equal(h.button('Xuất excel'), undefined)
    await h.w.act(async () => resolveFirst()); assert.deepEqual(h.rows(), [])
    assert.doesNotMatch(h.w.document.body.textContent, /Private old account/)
  } finally { await h.cleanup() }
})

test('account switch cancels an in-flight export before a private blob can download', async () => {
  let releaseBlob, exportSignal
  const h = await setup((url, options) => {
    if (url.pathname.endsWith('.xlsx')) {
      exportSignal = options.signal
      return { ok: true, headers: new Headers(), blob: () => new Promise(resolve => { releaseBlob = resolve }) }
    }
  })
  try {
    await h.w.act(async () => h.button('Xuất excel').click()); assert.ok(releaseBlob)
    await h.w.act(async () => h.w.mount({ ...user, permissions: { snapshot_today: true } }))
    assert.equal(exportSignal.aborted, true)
    await h.w.act(async () => releaseBlob(new h.w.Blob(['old account'])))
    assert.equal(h.w.downloaded, undefined)
  } finally { await h.cleanup() }
})

test('summary styles preserve mobile wrapping, selected border and focus', () => {
  const css = readFileSync('src/clear-borders.css', 'utf8')
  assert.match(css, /attendance-kpi[\s\S]*min-width: 0; min-height: 76px/)
  assert.match(css, /attendance-kpi\[aria-pressed="true"\][\s\S]*background: #205440/)
  assert.match(css, /attendance-kpi:focus-visible.*outline: 3px solid/)
})

test('changing group cancels the previous export without a delayed download', async () => {
  let releaseBlob, exportSignal
  const h = await setup((url, options) => {
    if (url.pathname.endsWith('.xlsx')) {
      exportSignal = options.signal
      return { ok: true, headers: new Headers(), blob: () => new Promise(resolve => { releaseBlob = resolve }) }
    }
  })
  try {
    await h.w.act(async () => h.button('Xuất excel').click())
    await h.click(2); assert.equal(exportSignal.aborted, true)
    assert.equal(h.button('Xuất excel').disabled, false)
    await h.w.act(async () => releaseBlob(new h.w.Blob(['old group'])))
    assert.equal(h.w.downloaded, undefined)
  } finally { await h.cleanup() }
})

test('new frontend fails closed on old backend without falling back to unfiltered export', async () => {
  let summaryRequests = 0, legacyRequests = 0
  const h = await setup(url => {
    if (url.pathname === '/v2/snapshot/export-summary.xlsx') {
      summaryRequests += 1
      return { ok: false, status: 404, json: async () => ({ detail: 'Not Found' }) }
    }
    if (url.pathname === '/v2/snapshot/export.xlsx') legacyRequests += 1
  })
  try {
    await h.click(2)
    await h.w.act(async () => h.button('Xuất excel').click())
    assert.equal(summaryRequests, 1); assert.equal(legacyRequests, 0)
    assert.equal(h.w.downloaded, undefined)
    assert.match(h.w.document.querySelector('.error-box').textContent, /Máy chủ chưa hỗ trợ xuất theo nhóm chấm công/)
    await h.click(0)
    await h.w.act(async () => h.button('Xuất excel').click())
    assert.equal(legacyRequests, 1)
    assert.equal(h.w.downloaded, 'VERA_ChamCong.xlsx')
  } finally { await h.cleanup() }
})
