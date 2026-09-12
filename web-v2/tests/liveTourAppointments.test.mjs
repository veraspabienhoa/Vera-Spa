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
const TODAY_VN = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date())
const TODAY_VN_LABEL = TODAY_VN.split('-').reverse().join('/')
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/LiveTourPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'mock-boundaries', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__tourTestApi;', loader: 'js' }))
b.onResolve({ filter: /^\.\.\/components\// }, (args) => /(ClearableSearchInput|LiveTour(AppointmentInput|ServiceActions|SearchSelect|TransactionDialog|PageItems|BookingDialog|CheckoutCustomer|TipInput))$/.test(args.path) ? undefined : ({ path: args.path, namespace: 'dialog' }))
    b.onLoad({ filter: /.*/, namespace: 'dialog' }, () => ({ contents: 'export default function Dialog(){return null}', loader: 'js' }))
  } }],
})

async function fixture({ canEdit = true, conflict = false, payable = false, setup, preserveStorage = false, role } = {}) {
  if (!preserveStorage) dom.window.localStorage.clear()
  const records = ['An An', 'An Bình'].map((name, i) => ({ _id: `e${i + 1}`, 'Tên nhân viên': name, 'STT': i + 1,
    'Lịch hẹn': i ? '' : '16:00', 'Vào ca': 'Ca 1', 'Trạng thái': '', 'Dịch vụ': '', 'Phòng': '',
    _tour_groups: ['working', 'available'], _payment_pending: payable && !i }))
  const data = { revision: 1, columns: ['STT', 'Tên nhân viên', 'Trạng thái', 'Phòng', 'Dịch vụ', 'Lịch hẹn', 'Vào ca'], records,
    capabilities: { appointment_edit: canEdit, operate: true, payment: true }, services: [{ id: 'body', name: 'Body 90', price: 100 }],
    state: { employees: payable ? [{ id: 'e1', name: 'An An', status: 'CHO THANH TOÁN', service: 'Body 90', room: '1.1', service_price: 100 }] : [] } }
  setup?.(data)
  const writes = []
  const exports = []
  let fail = conflict
  globalThis.__tourTestApi = {
    liveTour: async () => structuredClone(data),
    liveTourCustomerHistory: async (customerId) => ({ customer: structuredClone(data.customers.find((customer) => customer.id === customerId)), summary: { combo_remaining: 7 }, combo_purchases: structuredClone(data.customers.find((customer) => customer.id === customerId)?.combo_purchases || []), combo_usage: [{ id: 'u1', service: 'Body 90', business_date: TODAY_VN }], invoices: [], reports: [], pending: [] }),
    exportLiveTourExcel: async (kind, query) => { exports.push({ kind, query }) },
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
  await act(async () => root.render(React.createElement(module.exports.default, { user: { role: role || (canEdit ? 'letan' : 'nhanvien'), permissions: {} } })))
  const type = async (input, value) => act(() => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
  const search = () => document.querySelector('.tour-employee-search input')
  const quick = () => document.querySelector('.live-tour-appointment-editor.quick')
  const save = async (form) => act(async () => form.dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
  return { data, writes, exports, type, search, quick, save, dispose: async () => { await act(() => root.unmount()) } }
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

test('cleared board columns still show canonical service and room in checkout', async () => {
  const f = await fixture({ payable: true })
  try {
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    assert.match(document.querySelector('.tour-checkout-context').textContent, /An An.*1\.1/)
    assert.match(document.querySelector('.tour-transaction-dialog').textContent, /Body 90/)
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
    assert.equal(document.querySelectorAll('.tour-search-popup [role=option]').length, 36)
    assert.equal(document.querySelector('.tour-search-popup .tour-list-pages'), null)
    assert.ok(document.querySelector('.tour-search-popup').classList.contains('tour-search-scroll'))
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
    assert.ok(submit.classList.contains('primary-button'))
    assert.equal(dialog.querySelector('button[value="start"]'), null)
    await act(async () => submit.click())
    assert.equal(f.writes.length, 1)
    assert.equal(f.writes[0].action, 'update_booking')
    assert.equal(f.writes[0].payload.start_now, false)
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

test('prepaid combo checkout shows zero service charge while retaining service and employee', async () => {
  const f = await fixture({ payable: true, setup(data) {
    data.capabilities.customers_view = true
    data.customers = [{ id: 'c1', name: 'Khách Combo', phone: '0901234567', combo_purchases: [
      { id: 'cp1', combo_name: 'Combo 13', remaining: 13, total: 13 }] }]
    Object.assign(data.state.employees[0], { customer_id: 'c1', customer_name: 'Khách Combo', customer_phone: '0901234567' })
  } })
  try {
    await act(async () => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    const dialog = document.querySelector('.tour-transaction-dialog')
    const combo = [...dialog.querySelectorAll('label')].find(label => label.textContent.includes('Trừ vé combo')).querySelector('select')
    await act(() => { combo.value = 'cp1'; combo.dispatchEvent(new dom.window.Event('change', { bubbles: true })) })
    const totals = [...dialog.querySelectorAll('.live-tour-checkout-total strong')].map(node => node.textContent)
    assert.deepEqual(totals, ['0 đ', '0 đ', '0 đ'])
    assert.match(dialog.querySelector('.live-tour-checkout-entry').textContent, /An An.*Body 90.*0 đ/)
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


const inputFor = (label) => {
  const control = [...document.querySelectorAll('.tour-transaction-dialog label')].find((item) => item.textContent.trim() === label)
  return control?.htmlFor ? document.getElementById(control.htmlFor) : control?.querySelector('input')
}
const clickText = async (text, scope = document) => act(async () => {
  const button = [...scope.querySelectorAll('button')].find((item) => item.textContent.trim() === text)
  assert.ok(button, text)
  button.click()
})
const chooseOption = async (input, text, f) => {
  // Wait for the dialog's first-frame focus before simulating user input.
  await act(() => new Promise((resolve) => window.requestAnimationFrame(resolve)))
  await act(() => input.focus())
  await f.type(input, text)
  const option = [...document.querySelectorAll('.tour-search-popup [role=option]')].find((item) => item.textContent.includes(text))
  assert.ok(option, text)
  await act(() => option.click())
}

test('customer can be found by either field and selecting synchronizes both without stale identity', async () => {
  const f = await fixture({ payable: true, setup(data) {
    data.capabilities.customers_view = true
    data.customers = Array.from({ length: 12 }, (_, i) => ({ id: `c${i}`, name: `Khách ${i}`, phone: `09012345${String(i).padStart(2, '0')}` }))
  } })
  try {
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    await chooseOption(inputFor('Khách hàng'), 'Khách 11', f)
    assert.equal(inputFor('Điện thoại').value, '0901234511')
    await act(() => inputFor('Điện thoại').focus())
    await f.type(inputFor('Điện thoại'), '090 123 4502')
    assert.equal(inputFor('Khách hàng').value, '')
    const result = [...document.querySelectorAll('.tour-search-popup [role=option]')].find((item) => item.textContent.includes('Khách 2'))
    assert.ok(result)
    await act(() => result.click())
    assert.equal(inputFor('Khách hàng').value, 'Khách 2')
    assert.equal(inputFor('Điện thoại').value, '0901234502')
    await f.save(document.querySelector('.tour-transaction-dialog form'))
    assert.equal(f.writes[0].payload.customer_id, 'c2')
    assert.equal(f.writes[0].payload.customer_phone, '0901234502')
  } finally { await f.dispose() }
})

test('TIP has two exclusive rows, remembers default and sends only the selected TIP method', async () => {
  const f = await fixture({ payable: true, setup(data) {
    data.payment_settings = { auto_print: false, tip_cards: [{ id: 'tip50', name: '50.000 đ', amount: 50000 }] }
  } })
  try {
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    const tip = () => document.querySelector('.tour-tip-input')
    assert.equal(tip().querySelectorAll('.tour-tip-mode input[type=checkbox]').length, 2)
    await act(() => tip().querySelector('button[aria-label="Mặc định: Chọn thẻ tiền TIP"]').click())
    assert.deepEqual([...tip().querySelectorAll('.tour-tip-mode input')].map((input) => input.checked), [false, true])
    const card = tip().querySelector('.tour-tip-cards .tour-page-items-content button')
    assert.equal(card.textContent, '+ 50.000 đ')
    await act(() => card.click())
    await act(() => card.click())
    await act(() => tip().querySelector('[aria-label="Bỏ thẻ TIP 2"]').click())
    await act(() => card.click())
    await f.save(document.querySelector('.tour-transaction-dialog form'))
    assert.equal(f.writes[0].payload.tip, 0)
    assert.deepEqual(f.writes[0].payload.tip_card_ids, ['tip50', 'tip50'])
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    assert.equal(tip().querySelectorAll('.tour-tip-mode input')[1].checked, true)
    await act(() => tip().querySelectorAll('.tour-tip-mode input')[0].click())
    await f.type(inputFor('Tiền TIP'), '125000')
    await f.save(document.querySelector('.tour-transaction-dialog form'))
    assert.equal(f.writes[1].payload.tip, 125000)
    assert.deepEqual(f.writes[1].payload.tip_card_ids, [])
  } finally { await f.dispose() }
})

test('manual quick invoice chooses canonical staff, room, service and booking time without board selection', async () => {
  const f = await fixture({ setup(data) {
    data.capabilities.booking = true
    data.state.employees = [{ id: 'e1', name: 'An An', work_status: 'Đi làm', shift: 'Ca 1', service: '', status: '' }]
    data.state.rooms = [{ name: '1.1', active: true }]
  } })
  try {
    await act(() => document.querySelector('.tour-records-panel input[aria-label="Chọn An Bình"]').click())
    await clickText('Thanh toán nhanh')
    assert.deepEqual([...document.querySelectorAll('.tour-checkout-source button')].map(button => button.textContent), ['Thanh toán nhanh', 'Mua combo cho khách hàng'])
    await chooseOption(inputFor('Nhân viên'), 'An An', f)
    await chooseOption(inputFor('Phòng / giường'), '1.1', f)
    await chooseOption(inputFor('Dịch vụ'), 'Body 90', f)
    assert.equal(inputFor('Ngày booking').value, '')
    await f.type(inputFor('Ngày booking'), new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date()))
    await f.type(inputFor('Giờ booking'), '09:30')
    await f.save(document.querySelector('.tour-transaction-dialog form'))
    assert.equal(f.writes.length, 1)
    const body = f.writes[0], entry = body.payload.quick_booking
    assert.equal(body.action, 'quick_checkout')
    assert.equal(entry.employee_id, 'e1')
    assert.equal(entry.room, '1.1')
    assert.deepEqual(entry.service_items, [{ service_id: 'body', quantity: 1 }])
    assert.match(entry.booked_at, /T09:30:00\+07:00$/)
    assert.equal(body.payload.employee_ids, undefined)
    assert.equal(body.payload.total, undefined)
    assert.equal(body.row_ids, undefined)
  } finally { await f.dispose() }
})

test('quick checkout searches pending invoice by room and retains the selected invoice source', async () => {
  const f = await fixture({ payable: true, setup(data) {
    data.capabilities.pending_view = true; data.capabilities.invoice_view = true
    data.pending_payments = [{ id: 'p-old', customer_name: '', booked_at: `${TODAY_VN}T13:00:00+07:00`,
      entries: [{ employee_id: 'e1', employee_name: 'An An', room: '3.1', service: 'Body 90', price: 100, price_source: 'catalog', booked_at: `${TODAY_VN}T13:00:00+07:00`, started_at: `${TODAY_VN}T13:05:00+07:00` }] }]
  } })
  try {
    await act(() => [...document.querySelectorAll('.tour-records-panel input[type=checkbox]')][0].click())
    await act(() => document.querySelector('#live-tour-pending-panel .live-tour-card-actions .secondary-button').click())
    const picker = document.querySelector('.live-tour-employee-picker input')
    await chooseOption(picker, '3.1', f)
    assert.match(document.querySelector('.tour-checkout-context').textContent, /An An.*3\.1/)
    await f.save(document.querySelector('.tour-transaction-dialog form'))
    assert.equal(f.writes[0].payload.pending_id, 'p-old')
    assert.equal(f.writes[0].payload.employee_ids, undefined)
    assert.equal(f.writes[0].payload.quick_booking, undefined)
  } finally { await f.dispose() }
})

test('pending cards display staff-room-service and both booking and execution timestamps', async () => {
  const f = await fixture({ setup(data) {
    data.capabilities.pending_view = true; data.capabilities.invoice_view = true
    data.pending_payments = [{ id: 'p1', booked_at: `${TODAY_VN}T13:00:00+07:00`, entries: [{ employee_name: 'An An', room: '1.1', service: 'Body 90',
      booked_at: `${TODAY_VN}T13:00:00+07:00`, started_at: `${TODAY_VN}T13:05:00+07:00` }] }]
  } })
  try {
    const card = document.querySelector('#live-tour-pending-panel .live-tour-data-card')
    assert.match(card.textContent, /An An – 1\.1 – Body 90/)
    assert.match(card.textContent, /Khách lẻ/)
    assert.match(card.textContent, new RegExp(`Booking: 13:00 ${TODAY_VN_LABEL.replaceAll('/', '\\/')} · Thực hiện: 13:05 ${TODAY_VN_LABEL.replaceAll('/', '\\/')}`))
    assert.ok(!document.querySelector('input[placeholder="Nhập lịch hẹn…"]'))
  } finally { await f.dispose() }
})

test('board orders the standard start column across dates, ignoring remaining time and keeping leave last', async () => {
  const f = await fixture({ setup(data) {
    data.columns.push('TG bắt đầu thực hiện', 'TG CÒN LẠI', 'TG bắt đầu thực hiện YC')
    const template = data.records[0]
    data.records = [
      ['late', 'Mới bắt đầu', '01/10/2026 09:00:00', 1, ['doing']],
      ['leave', 'Nghỉ phép hôm nay', '01/08/2026 09:00:00', '', ['leave']],
      ['early', 'Bắt đầu trước', '30/09/2026 22:00:00', 120, ['doing']],
      ['paid', 'Đã thanh toán', '01/10/2026 08:00:00', '', ['working', 'available']],
      ['blank', 'Chưa thực hiện', '', '', ['working', 'available']],
    ].map(([id, name, start, remaining, groups], index) => ({ ...template, _id: id, STT: index + 1,
      'Tên nhân viên': name, 'TG bắt đầu thực hiện': start, 'TG CÒN LẠI': remaining,
      'TG bắt đầu thực hiện YC': '01/01/2026 00:00:00', _tour_groups: groups }))
  } })
  try {
    const names = () => [...document.querySelectorAll('.tour-records-panel tbody .tour-col-employee')].map((cell) => cell.textContent.trim())
    assert.deepEqual(names(), ['Chưa thực hiện', 'Bắt đầu trước', 'Đã thanh toán', 'Mới bắt đầu', 'Nghỉ phép hôm nay'])
    const leave = [...document.querySelectorAll('button.tour-metric-card')].find((button) => button.textContent.includes('Nghỉ phép'))
    assert.ok(leave)
    await act(() => leave.click())
    assert.deepEqual(names(), ['Nghỉ phép hôm nay'])
    assert.deepEqual([...document.querySelectorAll('.tour-records-panel tbody .tour-col-stt')].map((cell) => cell.textContent), ['1'])
  } finally { await f.dispose() }
})



test('room number search matches the entire room number and all beds, never another room bed suffix', async () => {
  const { roomOptionMatches } = await import('../src/lib/liveTourRooms.js')
  const options = ['1.1', '1.2', '1.6', '4', '4.1', '8.4', '10.4', '16.1', '16.2'].map(value => ({ value, label: value }))
  assert.deepEqual(options.filter(row => roomOptionMatches(row, '1')).map(row => row.value), ['1.1', '1.2', '1.6'])
  assert.deepEqual(options.filter(row => roomOptionMatches(row, '16')).map(row => row.value), ['16.1', '16.2'])
  assert.deepEqual(options.filter(row => roomOptionMatches(row, '4')).map(row => row.value), ['4', '4.1'])
  assert.deepEqual(options.filter(row => roomOptionMatches(row, 'Phòng 1')).map(row => row.value), ['1.1', '1.2', '1.6'])
  assert.deepEqual(options.filter(row => roomOptionMatches(row, '1.2')).map(row => row.value), ['1.2'])
})

test('PR hides a whole room while active, and other services annotate only the occupied bed', async () => {
  const { bookingRoomState } = await import('../src/lib/liveTourRooms.js')
  const rooms = ['1.1','1.2','16.1','16.2'].map(name => ({ name }))
  const catalog = [{ id: 'pr', name: '90 PR Tiêu chuẩn' }, { id: 'body', name: 'Body' }]
  for (const status of ['Đang chờ', 'Đang thực hiện', 'Đang sử dụng']) {
    const state = bookingRoomState(rooms, [{ id: 'other', room: '1.1', service: catalog[0].name, status }], catalog, 'new', '1.2')
    assert.deepEqual(state.options.map(row => row.value), ['16.1','16.2'])
    assert.match(state.error, /Phòng 1 đang bị khóa toàn phòng/)
  }
  const workers = [{ id: 'other', room: '1.1', service: 'Body', status: 'Đang chờ' }]
  const state = bookingRoomState(rooms, workers, catalog, 'new', '1.2')
  assert.equal(state.error, '')
  assert.ok(state.options[0].className && state.options[0].detail.includes('1.1: Body'))
  assert.equal(state.options[1].className, '')
  assert.ok(!state.options[1].detail.includes('1.1: Body'))
  assert.match(bookingRoomState(rooms, workers, catalog, 'new', '1.2', [{ service_id: 'pr' }]).error, /PR cần toàn phòng trống/)
  assert.match(bookingRoomState(rooms, workers, catalog, 'new', '1.1').error, /đang được sử dụng/)
  assert.equal(bookingRoomState(rooms, workers, catalog, 'other', '1.1').error, '')
  assert.equal(bookingRoomState(rooms, [{ ...workers[0], service: catalog[0].name, status: 'Chờ thanh toán' }], catalog, 'new', '1.1').options.length, 4)
  const custom = [{ name: 'Bed A', area_name: 'Phòng 16' }, { name: 'Bed B', area_name: 'Phòng 16' }]
  assert.equal(bookingRoomState(custom, [{ id: 'hidden', room: 'Bed A', service: 'Custom', private: true, status: 'Đang chờ' }], catalog, 'new', '').options.length, 0)
})

test('booking dropdown shows all room results and reports a PR collision immediately on selecting the room', async () => {
  const f = await fixture({ setup(data) {
    data.capabilities.booking = true
    data.services.push({ id: 'pr', name: '90 PR Tiêu chuẩn', price: 300000 })
    data.state.employees = [{ id:'e1', name:'An An', shift:'Ca 1', work_status:'Đi làm', service:'', status:'' },
      { id:'busy', room:'1.1', service:'Body 90', status:'Đang chờ' }]
    data.state.rooms = ['1.1','1.2','1.3','1.4','1.5','1.6','16.1','16.2','8.4'].map(name => ({name}))
  } })
  try {
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    await chooseOption(inputFor('Dịch vụ'), 'PR', f)
    const input = inputFor('Phòng / giường *')
    assert.equal(document.activeElement, input)
    assert.equal(input.getAttribute('aria-expanded'), 'true')
    assert.equal(document.querySelectorAll('.tour-search-scroll [role=option]').length, 9)
    await f.type(input, '1')
    assert.equal(document.querySelectorAll('.tour-search-scroll [role=option]').length, 6)
    assert.equal(document.querySelectorAll('.tour-room-option-occupied').length, 1)
    const option = [...document.querySelectorAll('.tour-search-scroll [role=option]')].find(row => row.textContent.startsWith('1.2'))
    await act(() => option.click())
    assert.equal(document.activeElement, input)
    assert.match(document.querySelector('.tour-booking-dialog [role=alert]').textContent, /PR cần toàn phòng trống/)
    assert.equal(f.writes.length, 0)
    assert.ok([...document.querySelectorAll('.tour-booking-dialog button[type=submit]')].every(button => button.disabled))
    await chooseOption(input, '16', f)
    assert.equal(document.querySelector('.tour-booking-dialog [role=alert]'), null)
    assert.equal(input.value, '16.1')
  } finally { await f.dispose() }
})

test('reception can explicitly share a PR room using only its free beds', async () => {
  const f = await fixture({ role: 'letan', setup(data) {
    data.capabilities.booking = true
    data.services.push({ id: 'pr', name: '90 PR Tiêu chuẩn', price: 300000 })
    data.state.employees = [{ id:'e1', name:'An An', shift:'Ca 1', work_status:'Đi làm', service:'', status:'' },
      { id:'busy', room:'2.1', service:'90 PR Tiêu chuẩn', status:'Đang chờ' }]
    data.state.rooms = ['2.1','2.2','4'].map(name => ({name}))
  } })
  try {
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    await chooseOption(inputFor('Dịch vụ'), 'PR', f)
    const input = inputFor('Phòng / giường *')
    await f.type(input, '2')
    assert.equal(document.querySelectorAll('.tour-search-scroll [role=option]').length, 0)
    const toggle = [...document.querySelectorAll('.tour-booking-dialog label')].find(label => label.textContent.includes('Cho khách dùng chung phòng PR')).querySelector('input')
    await act(() => toggle.click())
    await chooseOption(input, '2', f)
    assert.equal(input.value, '2.2')
    assert.equal(document.querySelector('.tour-booking-dialog [role=alert]'), null)
    await act(async () => document.querySelector('.tour-booking-dialog button[value=book]').click())
    assert.equal(f.writes[0].payload.room, '2.2')
    assert.equal(f.writes[0].payload.share_private_room, true)
  } finally { await f.dispose() }
})

test('booking advances on selection and Enter, skips quantities, and permits returning to add services', async () => {
  const f = await fixture({ setup(data) {
    data.capabilities.booking = true
    data.capabilities.customers_view = true
    data.customers = [{ id: 'c1', name: 'Khách Một', phone: '0901234567' }]
    data.services.push({ id: 'extra', name: 'Extra', price: 50 })
    data.state.employees = [{ id: 'e1', name: 'An An', service: '', status: '' }]
    data.state.rooms = [{ name: '1.1' }]
  } })
  try {
    await act(() => document.querySelector('.tour-records-panel .tour-col-employee button').click())
    await chooseOption(inputFor('Khách hàng'), 'Khách Một', f)
    const service = inputFor('Dịch vụ'), room = inputFor('Phòng / giường *')
    assert.equal(document.activeElement, service)
    assert.equal(service.getAttribute('aria-expanded'), 'true')
    await f.type(service, 'Body')
    assert.equal(document.activeElement, service)
    await act(() => service.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
    assert.equal(document.activeElement, room)
    assert.equal(room.getAttribute('aria-expanded'), 'true')
    await chooseOption(room, '1.1', f)
    const request = document.querySelector('.tour-booking-form select')
    assert.equal(document.activeElement, request)
    await act(() => { request.value = 'YC'; request.dispatchEvent(new dom.window.Event('change', { bubbles: true })) })
    assert.equal(document.activeElement, document.querySelector('.tour-booking-form textarea'))
    await chooseOption(service, 'Extra', f)
    assert.equal(document.querySelectorAll('.tour-booking-item').length, 2)
    assert.equal(document.activeElement, room)
    assert.equal(f.writes.length, 0)
  } finally { await f.dispose() }
})

test('admin bottom and direct STT actions target selected employee; manual order survives frontend sorting', async () => {
  const f = await fixture({ role: 'admin', setup(data) {
    data.records[0]._manual_order = true; data.records[0]._sort_index = 1
    data.records[1]._manual_order = true; data.records[1]._sort_index = 0
  } })
  try {
    const tableRows = [...document.querySelectorAll('.tour-records-panel tbody tr')]
    assert.ok(tableRows[0].textContent.includes('An Bình'))
    await act(() => tableRows[0].querySelector('input[type=checkbox]').click())
    await act(async () => [...document.querySelectorAll('button')].find(b => b.textContent === 'Xuống cuối').click())
    assert.equal(f.writes[0].action, 'admin_reorder')
    assert.equal(f.writes[0].payload.direction, 'bottom')
    assert.equal(document.querySelector('.tour-records-panel tbody input[type=checkbox]').checked, false)
    await act(() => document.querySelector('.tour-records-panel tbody input[type=checkbox]').click())
    await f.type(document.querySelector('input[aria-label="STT mới"]'), '1')
    await act(async () => [...document.querySelectorAll('button')].find(b => b.textContent === 'Đổi STT').click())
    assert.equal(f.writes[1].payload.position, 1)
    assert.equal(document.querySelector('.tour-records-panel tbody input[type=checkbox]').checked, false)
    const actions = [...document.querySelectorAll('.live-tour-controls-actions > button')].map(button => button.textContent.trim())
    assert.deepEqual(actions.slice(0, 10), [
      'Cập nhật lịch nghỉ', 'Thanh toán nhanh', 'Đi làm', 'Nghỉ phép',
      'Hủy Booking', 'Đổi nhân viên', 'Nghỉ giữa ca', 'Kết thúc nghỉ',
      'Xuống cuối', 'Lên đầu',
    ])
  } finally { await f.dispose() }
})

test('combo lookup opens directly, searches customers, exports Excel and opens history from customer cards', async () => {
  const f = await fixture({ role: 'admin', setup(data) {
    data.capabilities.customers_view = true
    data.capabilities.export = true
    data.capabilities.invoice_view = true
    data.capabilities.paid_invoice_view = true
    data.capabilities.pending_view = true
    data.capabilities.reports_view = true
    data.customers = [
      { id: 'c1', name: 'Anh Lưu', phone: '0919442626', combo_purchases: [{ id: 'cp1', combo_name: 'Combo PR', total: 8, used: 1, remaining: 7, price: 2500000, receptionist: 'Lễ tân A', purchased_at: `${TODAY_VN}T13:39:00+07:00` }] },
      { id: 'c2', name: 'Anh Hiền', phone: '0987653921', combo_purchases: [{ id: 'cp2', combo_name: 'Combo VIP', total: 10, remaining: 10, purchased_at: `${TODAY_VN}T14:06:00+07:00` }] },
    ]
  } })
  try {
    for (const label of ['Hóa đơn chờ thanh toán', 'Hóa đơn đã thanh toán', 'Báo cáo', 'Khách hàng', 'Gói Combo']) assert.ok([...document.querySelectorAll('.tour-heading-actions button')].some((button) => button.textContent.includes(label)))
    await clickText('Gói Combo')
    const search = document.querySelector('input[aria-label="Tìm khách hàng trong Gói Combo"]')
    assert.ok(search)
    assert.equal(document.querySelectorAll('.live-tour-combo-customer').length, 2)
    await f.type(search, '0919442626')
    assert.equal(document.querySelectorAll('.live-tour-combo-customer').length, 1)
    assert.match(document.querySelector('.live-tour-combo-customer').textContent, /Anh Lưu.*còn 7\/8 vé/s)
    await clickText('Xuất Excel', document.querySelector('.live-tour-combo-lookup'))
    assert.deepEqual(f.exports[0], { kind: 'customers', query: {} })
    await act(async () => document.querySelector('.live-tour-combo-customer').click())
    await act(() => new Promise((resolve) => setTimeout(resolve, 0)))
    assert.match(document.body.textContent, /Lịch sử khách hàng · Anh Lưu/)
    assert.equal(document.querySelector('[aria-label="Lọc thời gian lịch sử Combo"] select').value, 'month')
    assert.match(document.querySelector('.live-tour-history-sections').textContent, /Ngày mua:.*Gói dịch vụ combo:.*Combo PR.*Số vé đã mua:.*8.*Thành tiền:.*2\.500\.000.*Lễ tân:.*Lễ tân A.*Số vé đã sử dụng:.*1.*Số vé còn lại:.*7/s)
    assert.equal(document.querySelector('.live-tour-history-summary'), null)
    assert.match(document.body.textContent, /Lịch sử sử dụng vé Combo \(1\)/)
    assert.doesNotMatch(document.body.textContent, /Hóa đơn \(0\)|Dịch vụ \/ doanh thu|Phiếu chờ thanh toán/)
    await clickText('Xuất chi tiết khách hàng')
    assert.equal(f.exports[1].kind, 'customer_detail')
    assert.equal(f.exports[1].query.customer_id, 'c1')
    assert.match(f.exports[1].query.date_from, /^\d{4}-\d{2}-01$/)
    assert.match(f.exports[1].query.date_to, /^\d{4}-\d{2}-\d{2}$/)
  } finally { await f.dispose() }
})

test.after(() => dom.window.close())
