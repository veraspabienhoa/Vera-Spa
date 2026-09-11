import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { fitTransaction } from '../src/lib/transactionViewport.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LiveTourPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'mock-boundaries', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__tourTestApi;', loader: 'js' }))
    b.onResolve({ filter: /^\.\.\/components\// }, (args) => /LiveTour(AppointmentInput|ServiceActions|SearchSelect|TransactionDialog|PageItems|BookingDialog)$/.test(args.path) ? undefined : ({ path: args.path, namespace: 'dialog' }))
    b.onLoad({ filter: /.*/, namespace: 'dialog' }, () => ({ contents: 'export default function Dialog(){return null}', loader: 'js' }))
  } }],
})

async function fixture({ canEdit = true, conflict = false, payable = false, setup } = {}) {
  dom.window.localStorage.clear()
  const records = ['An An', 'An Bình'].map((name, i) => ({ _id: `e${i + 1}`, 'Tên nhân viên': name, 'STT': i + 1,
    'Lịch hẹn': i ? '' : '16:00', 'Vào ca': 'Ca 1', 'Trạng thái': '', 'Dịch vụ': '', 'Phòng': '',
    _tour_groups: ['working', 'available'], _payment_pending: payable && !i }))
  const data = { revision: 1, columns: ['STT', 'Tên nhân viên', 'Trạng thái', 'Phòng', 'Dịch vụ', 'Lịch hẹn', 'Vào ca'], records,
    capabilities: { appointment_edit: canEdit, operate: true, payment: true }, services: [{ id: 'body', name: 'Body 90', price: 100 }],
    state: { employees: payable ? [{ id: 'e1', name: 'An An', status: 'CHO THANH TOÁN', service: 'Body 90', room: '1.1', service_price: 100 }] : [] } }
  setup?.(data)
  const writes = []
  let fail = conflict
  globalThis.__tourTestApi = {
    liveTour: async () => structuredClone(data),
    liveTourAction: async (body) => {
      writes.push(body)
      if (fail) { fail = false; data.revision++; throw Object.assign(new Error('Live Tour đã thay đổi ở thiết bị khác. Hãy làm mới rồi thao tác lại.'), { status: 409 }) }
      assert.equal(body.expected_revision, data.revision)
      if (body.action !== 'update_appointment') return { ...structuredClone(data), ok: true }
      data.records.find((record) => record._id === body.payload.employee_id)['Lịch hẹn'] = body.payload.appointment
      data.revision++
      return structuredClone(data)
    },
  }
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(document.querySelector('#root'))
  await act(async () => root.render(React.createElement(module.exports.default, { user: { role: canEdit ? 'letan' : 'nhanvien', permissions: {} } })))
  const type = async (input, value) => act(() => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
  const search = () => document.querySelector('.tour-employee-search input')
  const quick = () => document.querySelector('.live-tour-appointment-editor.quick')
  const save = async (form) => act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
  return { data, writes, type, search, quick, save, dispose: async () => { await act(() => root.unmount()) } }
}

test('quick appointment sits beside search, rejects ambiguous names and saves only the exact employee', async () => {
  const f = await fixture()
  try {
    const headings = [...document.querySelectorAll('.tour-records-panel th')].map((cell) => cell.textContent)
    assert.equal(headings[headings.indexOf('Thao tác') + 1], 'Lịch hẹn')
    assert.equal(f.search().closest('.tour-employee-search').nextElementSibling, f.quick())
    assert.equal(f.quick().querySelector('input').disabled, true)
    await f.type(f.search(), 'an')
    assert.equal(f.quick().querySelector('input').disabled, true)
    await f.type(f.search(), 'an an')
    assert.equal(f.quick().querySelector('input').disabled, false)
    assert.match(f.quick().textContent, /An An/)
    await f.type(f.quick().querySelector('input'), '18:30 khách hẹn')
    await f.save(f.quick())
    assert.equal(f.writes.length, 1)
    assert.deepEqual(f.writes[0].payload, { employee_id: 'e1', employee_ids: ['e1'], appointment: '18:30 khách hẹn' })
    assert.ok(f.writes[0].idempotency_key)
    assert.equal(document.querySelector('.tour-records-panel input[aria-label="Lịch hẹn của An An"]').value, '18:30 khách hẹn')
    assert.equal(f.data.records[1]['Lịch hẹn'], '')
    await f.type(f.search(), 'an binh')
    assert.equal(f.quick().querySelector('input').value, '')
    assert.match(f.quick().textContent, /An Bình/)
  } finally { await f.dispose() }
})

test('inline editor preserves draft after revision conflict and retries only on explicit save', async () => {
  const f = await fixture({ conflict: true })
  try {
    const input = document.querySelector('.tour-records-panel input[aria-label="Lịch hẹn của An An"]')
    await f.type(input, '19:00')
    await f.save(input.form)
    assert.equal(f.writes.length, 1)
    assert.equal(input.value, '19:00')
    assert.equal(f.data.records[0]['Lịch hẹn'], '16:00')
    await f.save(input.form)
    assert.deepEqual(f.writes.map((body) => body.expected_revision), [1, 2])
    assert.equal(f.data.records[0]['Lịch hẹn'], '19:00')
    await f.type(input, '')
    await f.save(input.form)
    assert.equal(f.data.records[0]['Lịch hẹn'], '')
  } finally { await f.dispose() }
})

test('viewers without appointment capability see the value without an editor', async () => {
  const f = await fixture({ canEdit: false })
  try {
    assert.equal(document.querySelector('.live-tour-appointment-editor'), null)
    assert.equal(document.querySelector('.tour-records-panel td.tour-col-appointment').textContent, '16:00')
  } finally { await f.dispose() }
})

test('cleared board columns still show canonical service and room in quick checkout', async () => {
  const f = await fixture({ payable: true })
  try {
    await act(async () => [...document.querySelectorAll('button')].find((button) => button.textContent === 'Thanh toán nhanh').click())
    const picker = document.querySelector('.live-tour-employee-picker input')
    await act(() => picker.focus())
    const option = [...document.querySelectorAll('.tour-search-popup [role=option]')].find((item) => item.textContent.includes('An An'))
    assert.match(option.textContent, /An An.*Body 90.*1\.1/)
    await act(async () => option.click())
    assert.match(document.querySelector('.live-tour-employee-picked').textContent, /Body 90/)
  } finally { await f.dispose() }
})

test('employee dropdown selects one stable row and the appointment follows that selection', async () => {
  const f = await fixture()
  try {
    await act(() => f.search().focus())
    await f.type(f.search(), 'an')
    assert.equal(document.querySelectorAll('.tour-records-panel tbody input[type=checkbox]:checked').length, 0)
    const option = [...document.querySelectorAll('.tour-search-popup [role=option]')].find((item) => item.textContent.includes('An Bình'))
    await act(() => option.click())
    assert.equal(document.querySelector('.tour-search-popup'), null)
    assert.equal(f.search().value, 'An Bình')
    assert.equal(document.querySelectorAll('.tour-records-panel tbody tr').length, 1)
    assert.equal(document.querySelector('.tour-records-panel input[aria-label="Chọn An Bình"]').checked, true)
    await f.type(f.quick().querySelector('input'), '20:00')
    await f.save(f.quick())
    assert.equal(f.writes[0].payload.employee_id, 'e2')
    assert.equal(f.data.records[0]['Lịch hẹn'], '16:00')
    assert.equal(f.data.records[1]['Lịch hẹn'], '20:00')
  } finally { await f.dispose() }
})

test('duplicate employee names resolve by the option ID and every result remains reachable', async () => {
  const f = await fixture({ setup(data) {
    data.records = Array.from({ length: 35 }, (_, i) => ({ ...data.records[0], _id: `worker-${i}`, STT: i + 1, 'Tên nhân viên': 'An An', 'Lịch hẹn': '' }))
  } })
  try {
    await act(() => f.search().focus())
    assert.ok(document.querySelectorAll('.tour-search-popup [role=option]').length <= 6)
    const key = async (value) => act(() => f.search().dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true })))
    for (let i = 0; i < 34; i++) await key('ArrowDown')
    await key('Enter')
    assert.equal(document.querySelectorAll('.tour-records-panel tbody tr').length, 1)
    assert.equal(document.querySelector('.tour-records-panel tbody input[type=checkbox]').checked, true)
    await f.type(f.quick().querySelector('input'), '21:00')
    await f.save(f.quick())
    assert.equal(f.writes[0].payload.employee_id, 'worker-34')
    assert.equal(f.data.records[34]['Lịch hẹn'], '21:00')
    assert.ok(f.data.records.slice(0, 34).every((record) => record['Lịch hẹn'] === ''))
  } finally { await f.dispose() }
})

test('booking keeps all services in the payload while displaying a bounded list on one form', async () => {
  const f = await fixture({ setup(data) {
    const services = Array.from({ length: 7 }, (_, i) => ({ id: `service-${i}`, name: `Dịch vụ ${i}`, price: 100, duration: 90, active: true }))
    data.services = services
    data.state = { rooms: [{ name: '1.1', active: true }], employees: [{ id: 'e1', name: 'An An', work_status: 'Đi làm', shift: 'Ca 1',
      status: 'Đang chờ', service: 'Dịch vụ 0', room: '1.1', service_items: services.map((s) => ({ service_id: s.id, quantity: 1 })) }] }
  } })
  try {
    await act(async () => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    const dialog = document.querySelector('.tour-transaction-dialog')
    assert.ok(dialog)
    assert.equal(document.documentElement.style.overflow, 'hidden')
    assert.equal(dialog.querySelectorAll('.tour-booking-item').length, 2)
    await act(() => dialog.querySelector('button[aria-label="Dịch vụ đã chọn tiếp"]').click())
    await f.type(dialog.querySelector('.tour-booking-item input'), '3')
    const submit = [...dialog.querySelectorAll('button')].find((button) => button.textContent === 'Lưu dịch vụ')
    await act(async () => submit.click())
    assert.equal(f.writes.length, 1)
    assert.equal(f.writes[0].action, 'update_booking')
    assert.equal(f.writes[0].payload.service_items.length, 7)
    assert.equal(f.writes[0].payload.service_items[2].quantity, 3)
    assert.equal(document.querySelector('.tour-transaction-dialog'), null)
    assert.equal(document.documentElement.style.overflow, '')
  } finally { await f.dispose() }
})

test('payment keeps its fields and save button together, then restores the page after closing', async () => {
  const f = await fixture({ payable: true })
  try {
    await act(async () => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    const dialog = document.querySelector('.tour-transaction-dialog[aria-label="Thanh toán"]')
    assert.ok(dialog)
    for (const label of ['Khách hàng', 'Điện thoại', 'Phương thức thanh toán', 'Trừ vé combo', 'Số hóa đơn', 'Số vé', 'Giảm giá', 'Tiền TIP', 'Ghi chú']) assert.ok(dialog.textContent.includes(label), label)
    assert.ok(dialog.querySelector('button[type=submit]'))
    assert.equal(document.body.style.overflow, 'hidden')
    await act(async () => dialog.querySelector('button[aria-label="Đóng"]').click())
    assert.equal(document.body.style.overflow, '')
    assert.equal(document.querySelector('.tour-transaction-dialog'), null)
  } finally { await f.dispose() }
})

test('the complete form fits desktop, tablet, portrait, landscape and keyboard viewports', () => {
  for (const [width, height, contentHeight] of [[1440, 900, 660], [768, 1024, 670], [390, 844, 730], [320, 568, 760], [844, 390, 620], [390, 320, 730]]) {
    const contentWidth = Math.min(1040, width - 16)
    const fit = fitTransaction({ width, height }, contentWidth, contentHeight)
    assert.ok(fit.width <= width - 16 + .001)
    assert.ok(fit.height <= height - 16 + .001)
    assert.ok(fit.scale > 0 && fit.scale <= 1)
    assert.ok(Math.abs(fit.height / fit.width - contentHeight / contentWidth) < 1e-10)
  }
})

test('the mounted payment form refits when the visible viewport changes', async () => {
  const originalView = Object.getOwnPropertyDescriptor(dom.window, 'visualViewport')
  const originalHeight = Object.getOwnPropertyDescriptor(dom.window.HTMLElement.prototype, 'offsetHeight')
  const view = Object.assign(new dom.window.EventTarget(), { width: 390, height: 844, offsetTop: 0, offsetLeft: 0 })
  Object.defineProperty(dom.window, 'visualViewport', { configurable: true, value: view })
  Object.defineProperty(dom.window.HTMLElement.prototype, 'offsetHeight', { configurable: true, get() {
    return this.classList.contains('tour-transaction-dialog') ? 730 : 0
  } })
  const f = await fixture({ payable: true })
  try {
    await act(async () => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    const frame = document.querySelector('.tour-transaction-frame')
    assert.equal(Number(frame.dataset.scale), 1)
    view.height = 320
    await act(() => view.dispatchEvent(new dom.window.Event('resize')))
    assert.ok(Number(frame.dataset.scale) < 1)
    assert.ok(parseFloat(frame.style.height) <= 304)
    assert.ok(document.querySelector('.tour-transaction-dialog button[type=submit]'))
    assert.ok(document.querySelector('.tour-transaction-dialog textarea'))
    assert.equal(document.documentElement.style.overflow, 'hidden')
    view.width = 844; view.height = 390
    await act(() => view.dispatchEvent(new dom.window.Event('resize')))
    assert.ok(parseFloat(frame.style.height) <= 374)
    assert.ok(parseFloat(frame.style.width) <= 828)
  } finally {
    await f.dispose()
    if (originalView) Object.defineProperty(dom.window, 'visualViewport', originalView)
    else delete dom.window.visualViewport
    Object.defineProperty(dom.window.HTMLElement.prototype, 'offsetHeight', originalHeight)
  }
})

test.after(() => dom.window.close())
