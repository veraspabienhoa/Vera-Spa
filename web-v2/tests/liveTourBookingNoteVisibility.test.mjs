import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { EMPTY_REPORT_PAGE } from '../src/lib/liveTourReportPage.js'
import { defaultTourYesterdayFilters } from '../src/lib/liveTourFilters.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true }
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
const api = globalThis.__bookingNoteApi = {}
async function component(path) {
  const result = await build({
    entryPoints: [fileURLToPath(new URL(`../src/${path}.jsx`, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
    plugins: [{ name: 'booking-note-api-fixture', setup(b) {
      b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
      b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__bookingNoteApi;', loader: 'js' }))
    } }],
  })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const Receipt = await component('components/LiveTourReceipt')
const InvoiceChanges = await component('components/LiveTourInvoiceChanges')
const PaidDialog = await component('components/LiveTourPaidInvoiceDialog')
const Reports = await component('pages/LiveTourReportsPage')
const Customers = await component('pages/SpaManagementPage')
const date = defaultTourYesterdayFilters().date_from
const entries = [
  { employee_id: 'one', employee_name: 'An', room: 'Phòng 1', service: 'Body', price: 100, note: 'Nhẹ vai\nKhông dầu',
    service_items: [{ service_id: 'body', name: 'Body', quantity: 1, unit_price: 40 }, { service_id: 'foot', name: 'Foot', quantity: 1, unit_price: 60 }] },
  { employee_id: 'two', employee_name: 'Bình', room: 'Phòng 2', service: 'Foot', price: 200, note: 'Lực mạnh <img src=x onerror=alert(1)>' },
]
const invoice = { id: 'invoice', bill_no: 'VERA-TEST', customer_name: 'Khách thử', business_date: date,
  effective_at: `${date}T09:00:00+07:00`, total: 300, subtotal: 300, tip: 0, discount: 0,
  payment_method: 'TIỀN MẶT', note: 'Ghi chú chung đã thanh toán', entries }
async function mount(Component, props) {
  const root = createRoot(document.getElementById('root'))
  await act(async () => root.render(React.createElement(Component, props)))
  return { render: next => act(async () => root.render(React.createElement(Component, next))), close: () => act(async () => root.unmount()) }
}
async function click(text) {
  const button = [...document.querySelectorAll('button')].find(node => node.textContent.trim() === text || node.getAttribute('aria-label') === text)
  assert.ok(button, `Missing button: ${text}`)
  await act(async () => button.click())
}
function verifyEntryNotes(nodes) {
  assert.match(nodes[0].textContent, /An.*Phòng 1.*Ghi chú booking: Nhẹ vai\nKhông dầu/s)
  assert.doesNotMatch(nodes[0].textContent, /Lực mạnh/)
  assert.match(nodes[1].textContent, /Bình.*Phòng 2.*Ghi chú booking: Lực mạnh/s)
  assert.doesNotMatch(nodes[1].textContent, /Nhẹ vai/)
}

test('receipt prints each group booking snapshot once and keeps invoice note and amounts separate', async () => {
  const fixture = await mount(Receipt, { invoice, onClose() {} })
  try {
    const receipt = document.getElementById('live-tour-receipt')
    const rows = [...receipt.querySelectorAll('tbody tr')]
    assert.equal(rows.length, 3, 'notes must not add financial rows')
    verifyEntryNotes([rows[0], rows[2]])
    assert.doesNotMatch(rows[1].textContent, /Ghi chú booking/)
    assert.equal(receipt.textContent.split('Nhẹ vai').length - 1, 1)
    assert.match(receipt.textContent, /Ghi chú hóa đơn: Ghi chú chung đã thanh toán/)
    assert.deepEqual(rows.map(row => row.lastElementChild.textContent), ['40 đ', '60 đ', '200 đ'])
    assert.match(receipt.textContent, /Tổng tiền300 đ/)
    assert.equal(receipt.querySelector('img'), null, 'booking text must be escaped')
    await fixture.render({ invoice: { ...invoice, entries: entries.map(({ note: _note, ...entry }) => entry) }, onClose() {} })
    assert.doesNotMatch(receipt.textContent, /Ghi chú booking:/, 'legacy entries do not inherit the invoice note')
    assert.match(receipt.textContent, /Ghi chú hóa đơn: Ghi chú chung đã thanh toán/)
  } finally { await fixture.close() }
})

test('invoice audit shows before/after booking snapshots under the correct group entry', async () => {
  const after = { ...invoice, note: 'Sửa ghi chú hóa đơn', entries: [{ ...entries[0], note: '' }, entries[1]] }
  const fixture = await mount(InvoiceChanges, { changes: [{ id: 'edit', action: 'paid_invoice_update', before: invoice, after,
    at: `${date}T10:00:00+07:00`, actor: 'letan', reason: 'Điều chỉnh' }] })
  try {
    const before = [...document.querySelectorAll('h4')].find(node => node.textContent === 'Trước thay đổi').parentElement
    const changed = [...document.querySelectorAll('h4')].find(node => node.textContent === 'Sau thay đổi').parentElement
    verifyEntryNotes(before.querySelectorAll(':scope > div'))
    assert.match(before.textContent, /Ghi chú hóa đơn: Ghi chú chung đã thanh toán/)
    assert.match(changed.textContent, /Ghi chú hóa đơn: Sửa ghi chú hóa đơn/)
    assert.doesNotMatch(changed.textContent, /Nhẹ vai/)
    assert.match(changed.textContent, /Ghi chú booking: Lực mạnh/)
    assert.equal(document.querySelector('img'), null)
  } finally { await fixture.close() }
})

test('paid invoice editor exposes booking snapshots read-only and edits only the invoice note', async () => {
  const writes = []
  const fixture = await mount(PaidDialog, { context: { item: invoice, mode: 'edit', revision: 4 }, isAdmin: true,
    onClose() {}, onAction: async (...args) => { writes.push(args); return true } })
  try {
    verifyEntryNotes(document.querySelectorAll('.live-tour-data-card'))
    const noteLabel = [...document.querySelectorAll('label')].find(node => node.textContent.startsWith('Ghi chú hóa đơn'))
    assert.equal(noteLabel.querySelector('textarea').value, invoice.note)
    assert.equal(document.querySelectorAll('textarea').length, 2, 'booking snapshots have no editable fields')
    const field = noteLabel.querySelector('textarea')
    await act(async () => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value').set.call(field, 'Hóa đơn mới')
      field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    })
    await click('Lưu điều chỉnh hóa đơn')
    assert.equal(writes.length, 1)
    assert.equal(writes[0][1].note, 'Hóa đơn mới')
    assert.deepEqual(writes[0][1].entries, [])
    verifyEntryNotes(document.querySelectorAll('.live-tour-data-card'))
  } finally { await fixture.close() }
})

test('paid editor preserves long saved invoice notes unless the operator changes or explicitly clears them', async () => {
  const savedNote = `An: ${'ghi chú booking '.repeat(150)}\nBình: ${'không thay đổi '.repeat(150)}`
  assert.ok(savedNote.length > 2000)
  const writes = []
  const fixture = await mount(PaidDialog, { context: { item: { ...invoice, note: savedNote }, mode: 'edit', revision: 4 }, isAdmin: true,
    onClose() {}, onAction: async (...args) => { writes.push(args); return false } })
  try {
    const field = [...document.querySelectorAll('label')].find(node => node.textContent.startsWith('Ghi chú hóa đơn')).querySelector('textarea')
    assert.equal(field.value, savedNote, 'the existing note is not silently truncated to the input limit')
    assert.equal(field.maxLength, 2000)
    const method = document.querySelector('select')
    await act(async () => {
      method.value = 'THẺ'
      method.dispatchEvent(new dom.window.Event('change', { bubbles: true }))
    })
    await click('Lưu điều chỉnh hóa đơn')
    assert.equal(writes[0][1].payment_method, 'THẺ')
    assert.equal(Object.hasOwn(writes[0][1], 'note'), false, 'unrelated edits omit an unchanged long note')
    assert.equal(field.value, savedNote)
    for (const [index, next] of ['', 'Ghi chú đã rút gọn'].entries()) {
      await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value').set.call(field, next)
        field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
      })
      await click('Lưu điều chỉnh hóa đơn')
      assert.equal(Object.hasOwn(writes[index + 1][1], 'note'), true)
      assert.equal(writes[index + 1][1].note, next)
      assert.deepEqual(writes[index + 1][1].entries, [])
    }
    assert.equal(writes.length, 3)
  } finally { await fixture.close() }
})

for (const original of [undefined, null, '', 'Ghi chú sẵn có']) test(`paid editor omits unchanged ${JSON.stringify(original)} invoice note`, async () => {
  const writes = []
  const fixture = await mount(PaidDialog, { context: { item: { ...invoice, note: original }, mode: 'edit', revision: 4 }, isAdmin: true,
    onClose() {}, onAction: async (...args) => { writes.push(args); return true } })
  try {
    await click('Lưu điều chỉnh hóa đơn')
    assert.equal(writes.length, 1)
    assert.equal(Object.hasOwn(writes[0][1], 'note'), false)
  } finally { await fixture.close() }
})

test('report rows preserve distinct booking and invoice notes and open the matching receipt', async () => {
  let legacy = false
  api.liveTourReports = async () => ({ ...EMPTY_REPORT_PAGE, revision: 4, total: 2, invoices: [invoice],
    capabilities: { paid_invoice_view: true },
    rows: entries.map((entry, index) => ({ ...entry, id: `row-${index}`, invoice_id: invoice.id, bill_no: invoice.bill_no,
      effective_at: invoice.effective_at, booking_note: legacy ? undefined : entry.note, note: invoice.note })) })
  const fixture = await mount(Reports, { user: { role: 'admin' } })
  try {
    const rows = [...document.querySelectorAll('.live-tour-report-table tbody tr')]
    verifyEntryNotes(rows)
    for (const row of rows) assert.match(row.querySelector('[data-label="Hóa đơn / khách hàng"]').textContent, /Ghi chú hóa đơn: Ghi chú chung đã thanh toán/)
    assert.equal(document.querySelector('img'), null)
    await click('Xem')
    verifyEntryNotes([...document.querySelectorAll('#live-tour-receipt tbody tr')].filter((_, index) => index !== 1))
    await click('Đóng')
    legacy = true
    await click('Làm mới')
    const table = document.querySelector('.live-tour-report-table')
    assert.doesNotMatch(table.textContent, /Ghi chú booking/, 'historical rows never fill absent booking notes from another source')
    assert.match(table.textContent, /Ghi chú hóa đơn: Ghi chú chung đã thanh toán/)
  } finally { await fixture.close() }
})

test('customer service history keeps each booking note with employee/room and separate invoice notes', async () => {
  const customer = { id: 'customer', name: 'Khách thử', combo_purchases: [] }
  api.spaCustomers = async () => ({ customers: [customer], revision: 4, can_export: false })
  api.liveTourCustomerHistory = async () => ({ customer, capabilities: { paid_invoice_view: true, pending_view: true, invoice_view: true },
    summary: { invoice_count: 1, total_revenue: 300, combo_remaining_units: 0 }, combo_purchases: [],
    services: entries.map((entry, index) => ({ ...entry, id: `service-${index}`, business_date: date, bill_no: invoice.bill_no, invoice_note: invoice.note })),
    pending: [{ ...invoice, id: 'pending', note: 'Ghi chú hóa đơn chờ' }] })
  const fixture = await mount(Customers, { user: { role: 'admin' }, mode: 'customers' })
  try {
    await click('Lịch sử')
    const rows = [...document.querySelectorAll('.spa-history tbody tr')]
    assert.equal(rows.length, 2)
    for (let index = 0; index < rows.length; index++) {
      assert.match(rows[index].textContent, new RegExp(entries[index].employee_name))
      assert.match(rows[index].textContent, new RegExp(entries[index].room))
      assert.equal(rows[index].children[1].querySelector('small').textContent, `Ghi chú booking: ${entries[index].note}`)
      assert.equal(rows[index].children[0].querySelectorAll('small')[1].textContent, `Ghi chú hóa đơn: ${invoice.note}`)
      assert.doesNotMatch(rows[index].children[1].textContent, /Ghi chú chung đã thanh toán/)
    }
    const pending = document.querySelector('.spa-history > div:last-child')
    assert.match(pending.textContent, /Ghi chú hóa đơn: Ghi chú hóa đơn chờ/)
    verifyEntryNotes([...pending.querySelectorAll('p')].slice(1, 3))
    assert.equal(document.querySelector('img'), null)
    await click('Đóng')
    assert.equal(document.querySelector('.spa-history'), null)
    await click('Lịch sử')
    assert.match(document.querySelector('.spa-history').textContent, /Ghi chú booking: Nhẹ vai\nKhông dầu/)
  } finally { await fixture.close() }
})
