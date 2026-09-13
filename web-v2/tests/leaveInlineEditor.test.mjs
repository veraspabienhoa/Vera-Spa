import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { JSDOM } from 'jsdom'
import { LETAN_REASON_GROUPS, canEditLeaveRecord, canDeleteLeaveRecord, canChangeLeaveReason } from '../src/lib/leaveRecordPermissions.js'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LeaveRegistrationPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'lucide-react'],
  loader: { '.css': 'empty' },
  plugins: [{ name: 'mock-boundaries', setup(b) {
    b.onResolve({ filter: /\/lib\/(api|data|watchBell|pushNotifications)$/ }, (args) => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: {
      api: 'export const isApiConfigured = true; export const veraApi = globalThis.__leaveTestApi;',
      data: 'export const loadEmployees = async()=>[]; export const loadLeaveDailyStats = async()=>[]; export const loadLeaveReasons = async()=>[]; export const loadLeaveRecords = async()=>[];',
      watchBell: 'export const playWatchBellSound = async()=>true; export const unlockWatchBellAudio = async()=>true;',
      pushNotifications: 'export const disablePushNotifications = async()=>({}); export const enablePushNotifications = async()=>({}); export const readPushState = async()=>({supported:false}); export const syncExistingPushSubscription = async()=>({});',
    }[path], loader: 'js' }))
  } }],
})
const iso = (offset) => {
  const value = new Date(new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date()) + 'T12:00:00Z')
  value.setUTCDate(value.getUTCDate() + offset)
  return value.toISOString().slice(0, 10)
}
const policies = {
  employee_self_service_policy: { enabled: true, regular_notice_days: 3, unpaid_notice_days: 1 },
  letan_leave_policy: { enabled: true, groups: LETAN_REASON_GROUPS.map((reasons, index) => ({ id: `group_${index + 1}`, reasons })) },
}

async function fixture({ role = 'admin', records, catalog, failDate, setupApi }) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
  const names = ['window', 'document', 'navigator', 'IS_REACT_ACT_ENVIRONMENT', '__leaveTestApi']
  const descriptors = Object.fromEntries(names.map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  const dates = [], writes = []
  let failing = failDate
  const api = {
    leaveDailyStats: async () => ({ days: [] }),
    leaveRecords: async () => ({ records }),
    leaveReasons: async (date) => {
      dates.push(date)
      if (date === failing) throw Error('Tải lý do thất bại')
      return { reasons: catalog[date] || [], ...policies }
    },
    employees: async () => ({ employees: [] }), watchDates: async () => ({ dates: [] }),
    updateLeave: async (uid, payload) => { writes.push({ uid, payload }); return {} },
  }
  setupApi?.(api)
  const calls = []
  for (const name of ['leaveDailyStats', 'leaveRecords', 'leaveReasons', 'employees']) {
    const original = api[name]
    api[name] = (...args) => { calls.push([name, ...args]); return original(...args) }
  }
  Object.defineProperties(globalThis, {
    window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
    navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
    __leaveTestApi: { value: api, configurable: true },
  })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const Page = module.exports.default
  const root = createRoot(dom.window.document.querySelector('#root'))
  await act(async () => root.render(React.createElement(Page, { user: { role, employee_username: 'An An', permissions: { leave_manage_edit: true, leave_manage_delete: true } } })))
  return { dom, dates, writes, calls, retry: () => { failing = undefined },
    editor: (uid) => [...dom.window.document.querySelectorAll('.leave-records-table tbody tr')].find((row) => row.textContent.includes(uid))?.querySelector('.reason-edit-cell select'),
    dispose: async () => { await act(() => root.unmount()); dom.window.close(); for (const [key, value] of Object.entries(descriptors)) { if (value) Object.defineProperty(globalThis, key, value); else delete globalThis[key] } },
  }
}

test('Admin gets editors on historical rows across dates and saves the correct row/catalog penalty', async () => {
  const days = [iso(-3), iso(-2)]
  const records = days.map((date, i) => ({ record_uid: `uid-${i}`, employee_name: `Nhân viên ${i}`, leave_date: date, leave_reason: 'Lý do cũ', detail: `row-${i}`, leave_type: 'Vi phạm' }))
  const f = await fixture({ records, catalog: {
    [iso(0)]: [{ name: 'Chỉ cho hôm nay' }],
    [days[0]]: [{ name: 'Lý do cũ' }, { name: 'Vi phạm ngày cũ', requires_manual_penalty: true }],
    [days[1]]: [{ name: 'Lý do cũ' }, { name: 'Lý do ngày khác' }],
  } })
  try {
    const editor = f.editor('row-0')
    assert.ok(editor)
    assert.equal(editor.disabled, false)
    assert.deepEqual([...editor.options].map((o) => o.value), ['Lý do cũ', 'Vi phạm ngày cũ'])
    assert.deepEqual([...f.editor('row-1').options].map((o) => o.value), ['Lý do cũ', 'Lý do ngày khác'])
    assert.equal(f.dates.filter((d) => d === days[0]).length, 1)
    let prompted = false
    f.dom.window.prompt = () => { prompted = true; return '50000' }
    await act(() => { editor.value = 'Vi phạm ngày cũ'; editor.dispatchEvent(new f.dom.window.Event('change', { bubbles: true })) })
    const save = [...f.dom.window.document.querySelectorAll('button')].find((b) => b.textContent.includes('Lưu sửa'))
    assert.equal(save.disabled, false)
    await act(async () => save.click())
    assert.equal(prompted, true)
    assert.deepEqual(f.writes, [{ uid: 'uid-0', payload: { leave_reason: 'Vi phạm ngày cũ', manual_penalty: 50000 } }])
  } finally { await f.dispose() }
})

test('Lễ tân future editors are visible without changing the top date, with failure and retry', async () => {
  const day = iso(3)
  const f = await fixture({ role: 'letan', failDate: day, records: [{ record_uid: 'future', employee_name: 'An An', leave_date: day, leave_reason: 'Nghỉ CÓ phép', detail: 'future-row', leave_type: 'Có phép' }], catalog: { [day]: [{ name: 'Nghỉ CÓ phép' }, { name: 'Về sớm CÓ phép' }] } })
  try {
    assert.ok(f.editor('future-row'))
    assert.equal(f.editor('future-row').disabled, true)
    assert.match(f.dom.window.document.body.textContent, /Tải lý do thất bại/)
    f.retry()
    await act(async () => [...f.dom.window.document.querySelectorAll('button')].find((b) => b.textContent === 'Thử tải lại lý do').click())
    assert.equal(f.editor('future-row').disabled, false)
    assert.deepEqual([...f.editor('future-row').options].map((o) => o.value), ['Nghỉ CÓ phép', 'Về sớm CÓ phép'])
  } finally { await f.dispose() }
})

test('Employee notice boundaries distinguish editing to unpaid from deleting a paid row', () => {
  for (const role of ['nhanvien', 'leader', 'locker', 'tapvu']) {
    const context = { role, today: iso(0), recordDate: iso(1), currentReason: 'Nghỉ CÓ phép', currentLeaveType: 'Có phép', isOwnRecord: true, employeeSelfServicePolicy: policies.employee_self_service_policy }
    assert.equal(canEditLeaveRecord(context), true)
    assert.equal(canDeleteLeaveRecord(context), false)
    assert.equal(canChangeLeaveReason(context, { name: 'Nghỉ KHÔNG phép', leave_type: 'Không phép' }), true)
    assert.equal(canChangeLeaveReason(context, { name: 'Về sớm CÓ phép', leave_type: 'Có phép' }), false)
    assert.equal(canEditLeaveRecord({ ...context, isOwnRecord: false }), false)
    assert.equal(canEditLeaveRecord({ ...context, recordDate: iso(0) }), false)
    assert.equal(canDeleteLeaveRecord({ ...context, recordDate: iso(3) }), true)
  }
})

test('Employee row shows only reason changes that satisfy the one/three-day rule', async () => {
  const day = iso(1)
  const f = await fixture({ role: 'nhanvien', records: [{ record_uid: 'own', employee_name: 'An An', leave_date: day, leave_reason: 'Nghỉ CÓ phép', leave_type: 'Có phép', detail: 'own-row' }], catalog: { [day]: [
    { name: 'Nghỉ CÓ phép', leave_type: 'Có phép' }, { name: 'Về sớm CÓ phép', leave_type: 'Có phép' }, { name: 'Nghỉ KHÔNG phép', leave_type: 'Không phép' },
  ] } })
  try {
    const editor = f.editor('own-row')
    assert.ok(editor)
    assert.deepEqual([...editor.options].map((o) => o.value), ['Nghỉ CÓ phép', 'Nghỉ KHÔNG phép'])
    assert.equal(f.dom.window.document.querySelector('.select-column input').disabled, true)
  } finally { await f.dispose() }
})

test('records become visible before a slow catalog and keep editors disabled until it arrives', async () => {
  let completeCatalog
  const pendingCatalog = new Promise((resolve) => { completeCatalog = resolve })
  const day = iso(0)
  const f = await fixture({ records: [{ record_uid: 'early', employee_name: 'An An', leave_date: day, leave_reason: 'Nghỉ CÓ phép', detail: 'visible-before-catalog' }], catalog: {},
    setupApi(api) { api.leaveReasons = () => pendingCatalog } })
  try {
    assert.ok(f.editor('visible-before-catalog'))
    assert.equal(f.editor('visible-before-catalog').disabled, true)
    assert.equal(f.dom.window.document.querySelector('.leave-list-wrap').getAttribute('aria-busy'), 'false')
    assert.match(f.dom.window.document.querySelector('.leave-form').textContent, /Đang tải lý do nghỉ/)
    assert.ok(!f.calls.some(([name]) => name === 'employees'))
    await act(async () => completeCatalog({ reasons: [{ name: 'Nghỉ CÓ phép' }], ...policies }))
    assert.equal(f.editor('visible-before-catalog').disabled, false)
    assert.equal(f.calls.filter(([name]) => name === 'employees').length, 1)
  } finally { completeCatalog({ reasons: [], ...policies }); await f.dispose() }
})

test('changing statistics reloads only statistics and preserves unsaved row edits', async () => {
  const day = iso(0)
  const f = await fixture({ records: [{ record_uid: 'draft', employee_name: 'An An', leave_date: day, leave_reason: 'Nghỉ CÓ phép', detail: 'draft-row' }],
    catalog: { [day]: [{ name: 'Nghỉ CÓ phép' }, { name: 'Về sớm CÓ phép' }] } })
  try {
    const editor = f.editor('draft-row')
    await act(() => { editor.value = 'Về sớm CÓ phép'; editor.dispatchEvent(new f.dom.window.Event('change', { bubbles: true })) })
    f.calls.length = 0
    await act(async () => [...f.dom.window.document.querySelectorAll('.statistics-filter-toolbar button')].find((button) => button.textContent === 'Tuần này').click())
    assert.deepEqual(f.calls.map(([name]) => name), ['leaveDailyStats'])
    assert.equal(f.editor('draft-row').value, 'Về sớm CÓ phép')
    f.calls.length = 0
    await act(async () => [...f.dom.window.document.querySelectorAll('.leave-list-panel button')].find((button) => button.textContent === 'Tuần sau').click())
    assert.deepEqual(f.calls.map(([name]) => name), ['leaveRecords'])
  } finally { await f.dispose() }
})

test('loading is distinguished from empty data and a statistics failure still loads the list', async () => {
  let failStatistics
  const statistics = new Promise((_, reject) => { failStatistics = reject })
  const day = iso(0)
  const f = await fixture({ records: [{ record_uid: 'independent', employee_name: 'An An', leave_date: day, leave_reason: 'Nghỉ CÓ phép', detail: 'survives-stats-error' }],
    catalog: { [day]: [{ name: 'Nghỉ CÓ phép' }] }, setupApi(api) { api.leaveDailyStats = () => statistics } })
  try {
    assert.match(f.dom.window.document.querySelector('.daily-summary-wrap').textContent, /Đang tải thống kê lịch nghỉ/)
    assert.match(f.dom.window.document.querySelector('.leave-list-wrap').textContent, /Đang tải danh sách lịch nghỉ/)
    assert.ok(!f.dom.window.document.querySelector('.leave-list-wrap').textContent.includes('Không có lịch nghỉ'))
    await act(async () => failStatistics(Error('Tạm thời không tải được thống kê')))
    assert.match(f.dom.window.document.querySelector('.daily-summary-wrap').textContent, /Chưa tải được thống kê/)
    assert.ok(f.editor('survives-stats-error'))
    assert.equal(f.editor('survives-stats-error').disabled, false)
  } finally { await f.dispose() }
})

test('a delayed save refreshes the current filters instead of reopening the earlier range', async () => {
  let completeSave
  const saved = new Promise((resolve) => { completeSave = resolve })
  const day = iso(0)
  const f = await fixture({ records: [{ record_uid: 'save', employee_name: 'An An', leave_date: day, leave_reason: 'Nghỉ CÓ phép', detail: 'saving-row' }],
    catalog: { [day]: [{ name: 'Nghỉ CÓ phép' }, { name: 'Về sớm CÓ phép' }] }, setupApi(api) { api.updateLeave = () => saved } })
  try {
    const editor = f.editor('saving-row')
    await act(() => { editor.value = 'Về sớm CÓ phép'; editor.dispatchEvent(new f.dom.window.Event('change', { bubbles: true })) })
    await act(async () => [...f.dom.window.document.querySelectorAll('button')].find((button) => button.textContent.includes('Lưu sửa')).click())
    f.calls.length = 0
    await act(async () => [...f.dom.window.document.querySelectorAll('.statistics-filter-toolbar button')].find((button) => button.textContent === 'Tuần sau').click())
    const currentRange = f.calls.find(([name]) => name === 'leaveDailyStats').slice(1)
    f.calls.length = 0
    await act(async () => completeSave({}))
    assert.deepEqual(f.calls.find(([name]) => name === 'leaveDailyStats').slice(1), currentRange)
    assert.match(f.dom.window.document.body.textContent, /LƯU SỬA THÀNH CÔNG/)
  } finally { completeSave({}); await f.dispose() }
})
