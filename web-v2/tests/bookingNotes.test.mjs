import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { bookingNotesDefault, checkoutNote } from '../src/lib/liveTourNotes.js'

const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
window.HTMLElement.prototype.scrollIntoView = () => {}
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
async function component(path, plugins = []) {
  const built = await build({ entryPoints: [`src/${path}.jsx`], bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' }, plugins })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const Booking = await component('components/LiveTourBookingDialog')
const Pending = await component('components/LiveTourPendingDialog')
const Page = await component('pages/LiveTourPage', [{ name: 'fixtures', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onResolve({ filter: /\/components\/LiveTourPendingPanel$/ }, () => ({ path: 'panel', namespace: 'fixture' }))
  b.onLoad({ filter: /api/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = {liveTour:(...args)=>globalThis.__notesApi.liveTour(...args),liveTourCollection:(...args)=>globalThis.__notesApi.liveTourCollection(...args),liveTourAction:(...args)=>globalThis.__notesApi.liveTourAction(...args)};' }))
  // Expose the existing quick-source picker and selected-row checkout entry
  // points without coupling this regression to the board's table selection UI.
  b.onLoad({ filter: /panel/, namespace: 'fixture' }, () => ({ loader: 'jsx', contents: `
    export default function Panel({openModal, pendingPayments}) { return <div>
      {pendingPayments.map(item=><button key={item.id} onClick={()=>openModal('checkout',{item,rowIds:[]})}>Pay {item.id}</button>)}
      <button onClick={()=>openModal('checkout',{rowIds:['e1','e2']})}>Pay group</button>
      <button onClick={()=>openModal('quick_checkout',{rowIds:[]})}>Choose quick source</button>
    </div> }` }))
} }])
const services = [{ id: 'body', name: 'Body', price: 100, duration: 60, active: true }]
const employees = [
  { id: 'e1', name: 'An', shift: 'Ca 1', work_status: 'Đi làm', service: 'Body', service_items: [{ service_id: 'body', quantity: 1, unit_price: 100 }], service_price: 100, room: '1.1', status: 'Đang thực hiện', note: 'Nhẹ vai trái' },
  { id: 'e2', name: 'Bình', shift: 'Ca 1', work_status: 'Đi làm', service: 'Body', service_items: [{ service_id: 'body', quantity: 1, unit_price: 100 }], service_price: 100, room: '1.2', status: 'Đang thực hiện', note: 'Không dùng dầu' },
]
const entries = employees.map(e => ({ ...e, employee_id: e.id, employee_name: e.name, price: 100 }))
const pending = { id: 'p1', created_at: new Date().toISOString(), note: 'Ghi chú chung', entries }
const baseData = { revision: 7, services, state: { employees, rooms: [{ name: '1.1' }, { name: '1.2' }] }, payment_settings: {} }
const click = async node => { assert.ok(node); await act(async () => node.click()) }
const button = text => [...document.querySelectorAll('button')].find(node => node.textContent.trim() === text)
const field = label => [...document.querySelectorAll('[role="dialog"] label')].find(node => node.querySelector('span')?.textContent.trim() === label)?.querySelector('textarea')
async function type(node, value) {
  assert.ok(node)
  await act(() => {
    const prototype = node.tagName === 'TEXTAREA' ? window.HTMLTextAreaElement.prototype : window.HTMLInputElement.prototype
    Object.getOwnPropertyDescriptor(prototype, 'value').set.call(node, value)
    node.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
}
async function mount(Component, props) {
  const root = createRoot(document.querySelector('#root'))
  await act(async () => root.render(React.createElement(Component, props)))
  return { root, render: async next => act(async () => root.render(React.createElement(Component, next))), dispose: async () => act(() => root.unmount()) }
}
const bookingProps = { data: baseData, context: { employeeId: 'e1' }, canBook: true, canOperate: true, canPayment: true, onClose() {}, onCheckout() {} }

test('invoice defaults preserve all distinct booking notes and intentional emptiness', () => {
  assert.equal(bookingNotesDefault([...entries, entries[0], { note: '  ' }]), 'Nhẹ vai trái\nKhông dùng dầu')
  assert.equal(checkoutNote({ entries }), 'Nhẹ vai trái\nKhông dùng dầu')
  assert.equal(checkoutNote({ note: '', entries }), '')
  assert.equal(checkoutNote({ note: 'Invoice only', entries }), 'Invoice only')
  assert.equal(checkoutNote(undefined, []), '')
})

test('waiting booking reopens saved note, cancel discards draft, explicit clear submits and new booking starts blank', async () => {
  const writes = [], worker = { ...employees[0], status: 'Đang chờ' }
  const props = { ...bookingProps, data: { ...baseData, state: { ...baseData.state, employees: [worker] } }, onAction: async (...args) => { writes.push(args); return true } }
  const view = await mount(Booking, props)
  try {
    assert.equal(field('Ghi chú').value, worker.note)
    await type(field('Ghi chú'), 'Unsaved')
    await click(button('Đóng'))
    assert.equal(writes.length, 0)
    await view.render({ ...props, key: 'reopen' })
    assert.equal(field('Ghi chú').value, worker.note)
    await type(field('Ghi chú'), '')
    await click(button('Lưu dịch vụ'))
    assert.equal(writes[0][0], 'update_booking')
    assert.equal(writes[0][1].note, '')
    await view.render({ ...props, key: 'new', data: { ...baseData, state: { ...baseData.state, employees: [{ ...worker, service: '', service_items: [], status: '' }] } } })
    assert.equal(field('Ghi chú').value, '', 'an idle employee must not carry the last customer note')
  } finally { await view.dispose() }
})

test('finish includes edited note, completion shows it and routes edits through pending revision', async () => {
  const writes = [], edits = []
  const props = { ...bookingProps, canInvoiceEdit: true, onPendingEdit: (...args) => edits.push(args), onAction: async (...args) => {
    writes.push(args)
    return { revision: 8, result: { pending: { ...pending, note: args[1].note, entries: [{ ...entries[0], note: args[1].note }] } } }
  } }
  const view = await mount(Booking, props)
  try {
    await type(field('Ghi chú'), 'Đã sửa trước khi hoàn thành')
    await click(button('Hoàn thành'))
    assert.equal(writes[0][0], 'finish_to_pending')
    assert.equal(writes[0][1].note, 'Đã sửa trước khi hoàn thành')
    assert.equal(field('Ghi chú hóa đơn').value, writes[0][1].note)
    assert.equal(field('Ghi chú hóa đơn').readOnly, true)
    assert.match(document.querySelector('[aria-label="Ghi chú booking"]').textContent, /An · 1.1: Đã sửa trước khi hoàn thành/)
    await click(button('Sửa ghi chú hóa đơn'))
    assert.equal(edits[0][0].id, 'p1')
    assert.equal(edits[0][1], 8)
    await view.render({ ...props, canInvoiceEdit: false })
    assert.equal(button('Sửa ghi chú hóa đơn'), undefined)
  } finally { await view.dispose() }
})

test('legacy completed assignment displays its note and requires payment plus invoice-edit to move then edit', async () => {
  const writes = [], edits = []
  const props = { ...bookingProps, canInvoiceEdit: false, data: { ...baseData, state: { ...baseData.state, employees: [{ ...employees[0], status: 'CHO THANH TOÁN' }] } }, onAction: async (...args) => {
    writes.push(args); return { revision: 9, result: { pending } }
  }, onPendingEdit: (...args) => edits.push(args) }
  const view = await mount(Booking, props)
  try {
    assert.equal(field('Ghi chú booking').value, employees[0].note)
    assert.equal(field('Ghi chú booking').readOnly, true)
    assert.equal(button('Chuyển sang hóa đơn chờ để sửa ghi chú'), undefined)
    await view.render({ ...props, canInvoiceEdit: true, canPayment: false })
    assert.equal(button('Chuyển sang hóa đơn chờ để sửa ghi chú'), undefined)
    await view.render({ ...props, canInvoiceEdit: true })
    await click(button('Chuyển sang hóa đơn chờ để sửa ghi chú'))
    assert.deepEqual(writes[0], ['move_pending', { employee_id: 'e1' }, [], { expectedRevision: 7 }])
    assert.deepEqual(edits[0], [pending, 9])
  } finally { await view.dispose() }
})

test('pending view cannot submit; reopening editor preserves separate source notes and saved clear', async () => {
  const writes = []
  const props = { context: { item: pending, mode: 'view', revision: 7 }, catalog: services, isAdmin: true, onClose() {}, onAction: async (...args) => { writes.push(args); return true } }
  const view = await mount(Pending, props)
  try {
    assert.match(document.querySelector('[aria-label="Ghi chú booking"]').textContent, /An · 1.1: Nhẹ vai trái.*Bình · 1.2: Không dùng dầu/)
    assert.match(document.body.textContent, /Ghi chú hóa đơn: Ghi chú chung/)
    assert.equal(document.querySelector('button[type="submit"]'), null)
    await act(() => document.querySelector('form').dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true })))
    assert.equal(writes.length, 0)
    const editProps = { ...props, key: 'edit', context: { ...props.context, mode: 'edit' } }
    await view.render(editProps)
    await type(field('Ghi chú hóa đơn'), 'Unsaved')
    await click(button('Đóng'))
    assert.equal(writes.length, 0)
    await view.render({ ...editProps, key: 'reopen' })
    assert.equal(field('Ghi chú hóa đơn').value, pending.note)
    await type(field('Ghi chú hóa đơn'), '')
    await click(button('Lưu sửa hóa đơn'))
    assert.equal(writes[0][0], 'pending_update')
    assert.equal(writes[0][1].note, '')
    assert.deepEqual(writes[0][1].entries, [])
    assert.deepEqual(writes[0][3], { expectedRevision: 7 })
    await view.render({ ...editProps, key: 'saved', context: { ...editProps.context, item: { ...pending, note: '' } } })
    assert.equal(field('Ghi chú hóa đơn').value, '')
    assert.match(document.querySelector('[aria-label="Ghi chú booking"]').textContent, /Nhẹ vai trái.*Không dùng dầu/)
  } finally { await view.dispose() }
})

async function pageFixture(options = {}) {
  window.localStorage.clear()
  window.sessionStorage.clear()
  const workers = employees.map(e => ({ ...e, status: options.doing ? 'Đang thực hiện' : 'CHO THANH TOÁN' }))
  const bills = [pending, { id: 'p2', created_at: new Date().toISOString(), entries: [{ ...entries[1], note: 'Khách thứ hai' }] }, { id: 'p3', created_at: new Date().toISOString(), note: '', entries }]
  let data = { ...baseData, columns: ['STT', 'Tên nhân viên', 'Vào ca', 'Dịch vụ', 'Phòng', 'Trạng thái'],
    records: workers.map((e, index) => ({ STT: index + 1, _id: e.id, _employee_id: e.id, 'Tên nhân viên': e.name, 'Vào ca': 'Ca 1', 'Dịch vụ': 'Body', 'Phòng': e.room, 'Trạng thái': e.status })),
    state: { ...baseData.state, employees: workers, pending: bills }, pending_payments: bills, customers: [],
    capabilities: { payment: true, booking: true, customers_view: false, pending_view: true, invoice_view: true },
  }
  const writes = [], accepted = []
  const originalBoard = data
  const detail = () => options.detailData ? options.detailData(data) : data
  globalThis.__notesApi = { liveTour: async () => options.holdBoard ? originalBoard : data,
    liveTourCollection: async () => ({ data: detail(), revision: detail().revision, page: 1, pages: 1, total: bills.length }),
    liveTourAction: async body => {
      writes.push(body)
      if (options.enforceCas && body.expected_revision !== detail().revision) {
        throw Object.assign(new Error('Live Tour đã thay đổi ở thiết bị khác. Hãy làm mới rồi thao tác lại.'), { status: 409, payload: { code: 'revision_conflict' } })
      }
      accepted.push(body)
      if (options.finishResult && body.action === 'finish_to_pending') {
        data = { ...data, revision: data.revision + 1 }
        return { ...data, result: { pending: { ...pending, note: body.payload.note ?? employees[0].note } } }
      }
      return { ...data, result: { invoice: { id: 'paid', bill_no: 'TEST', note: body.payload.note, entries, total: 200, subtotal: 200 } } }
    } }
  const view = await mount(Page, { user: { role: 'admin' } })
  await click([...document.querySelectorAll('button')].find(node => node.textContent.startsWith('Hóa đơn chờ thanh toán')))
  await act(async () => new Promise(resolve => setTimeout(resolve, 230)))
  return { ...view, writes, accepted, current: () => data, replace: value => { data = value } }
}

async function chooseSource(text, matchIndex = 0) {
  const label = [...document.querySelectorAll('[role="dialog"] label')].find(node => node.textContent === 'Tìm nhân viên / phòng / dịch vụ chờ thanh toán')
  const input = document.getElementById(label.htmlFor)
  await act(() => { input.focus(); input.dispatchEvent(new window.FocusEvent('focusin', { bubbles: true })) })
  await click([...document.querySelectorAll('[role="option"]')].filter(node => node.textContent.includes(text))[matchIndex])
}

test('checkout opens pending or grouped notes; edits survive refresh and cancel/reopen resets source defaults', async () => {
  const view = await pageFixture()
  try {
    await click(button('Pay p1'))
    assert.equal(field('Ghi chú hóa đơn').value, pending.note)
    assert.match(document.querySelector('[aria-label="Ghi chú booking"]').textContent, /An · 1.1: Nhẹ vai trái.*Bình · 1.2: Không dùng dầu/)
    await type(field('Ghi chú hóa đơn'), '')
    await act(async () => window.dispatchEvent(new window.Event('vera:leave-updated')))
    assert.equal(field('Ghi chú hóa đơn').value, '', 'refresh must not restore an intentionally cleared draft')
    await click(button('Hủy'))
    assert.equal(view.writes.length, 0)
    await click(button('Pay p1'))
    assert.equal(field('Ghi chú hóa đơn').value, pending.note)
    await click(button('Hủy'))
    await click(button('Pay p3'))
    assert.equal(field('Ghi chú hóa đơn').value, '', 'saved empty invoice note takes precedence over entry notes')
    await click(button('Hủy'))
    await click(button('Pay group'))
    assert.equal(field('Ghi chú hóa đơn').value, 'Nhẹ vai trái\nKhông dùng dầu')
    await type(field('Ghi chú hóa đơn'), '')
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes[0].action, 'checkout')
    assert.equal(view.writes[0].payload.note, '')
    assert.deepEqual(view.writes[0].payload.employee_ids, ['e1', 'e2'])
  } finally { await view.dispose() }
})

test('quick source switching replaces previous draft and manual checkout never inherits a live booking note', async () => {
  const view = await pageFixture()
  try {
    await click(button('Choose quick source'))
    await chooseSource('An, Bình')
    assert.equal(field('Ghi chú hóa đơn').value, pending.note)
    await type(field('Ghi chú hóa đơn'), 'Draft for first source')
    await chooseSource('Bình', 2)
    assert.equal(field('Ghi chú hóa đơn').value, 'Khách thứ hai')
    await chooseSource('An, Bình', 1)
    assert.equal(field('Ghi chú hóa đơn').value, '')
    await chooseSource('Bình')
    // The employee entry appears first and has its own source note.
    assert.equal(field('Ghi chú hóa đơn').value, employees[1].note)
    await click([...document.querySelectorAll('[role="dialog"] button')].find(node => node.textContent.trim() === 'Thanh toán nhanh'))
    assert.equal(field('Ghi chú hóa đơn').value, '')
    await type(field('Ghi chú hóa đơn'), 'Manual note')
    await click([...document.querySelectorAll('[role="dialog"] button')].find(node => node.textContent.trim() === 'Thanh toán nhanh'))
    assert.equal(field('Ghi chú hóa đơn').value, 'Manual note', 'reselecting the same manual mode must not erase a draft')
    await click(button('Hủy'))
    await click(button('Choose quick source'))
    assert.equal(field('Ghi chú hóa đơn').value, '')
  } finally { await view.dispose() }
})

test('pending editor retains an unchanged long grouped note and still permits shortening or clearing', async () => {
  const longNote = `${'A'.repeat(1500)}\n${'B'.repeat(1500)}`
  const writes = []
  const props = { context: { mode: 'edit', revision: 7, item: { ...pending, note: longNote } }, catalog: services,
    isAdmin: true, onClose() {}, onAction: async (...args) => { writes.push(args); return true } }
  const view = await mount(Pending, props)
  try {
    assert.equal(field('Ghi chú hóa đơn').value, longNote)
    await click(button('Lưu sửa hóa đơn'))
    assert.equal(Object.hasOwn(writes[0][1], 'note'), false, 'unrelated edits must not resubmit a long default to the 2000-character validation')
    await type(field('Ghi chú hóa đơn'), 'Ghi chú rút gọn')
    await click(button('Lưu sửa hóa đơn'))
    assert.equal(writes[1][1].note, 'Ghi chú rút gọn')
    await type(field('Ghi chú hóa đơn'), '')
    await click(button('Lưu sửa hóa đơn'))
    assert.equal(writes[2][1].note, '')
  } finally { await view.dispose() }
})

async function refreshBoard() {
  await act(async () => window.dispatchEvent(new window.Event('vera:leave-updated')))
  // Board and independently debounced detail responses can settle separately.
  await act(async () => new Promise(resolve => setTimeout(resolve, 230)))
}

for (const source of ['group', 'pending']) test(`${source} checkout keeps frozen revision and clear when another operator changes source`, async () => {
  const view = await pageFixture({ enforceCas: true })
  try {
    await click(button(source === 'group' ? 'Pay group' : 'Pay p1'))
    await type(field('Ghi chú hóa đơn'), '')
    const previous = view.current()
    const nextEmployees = previous.state.employees.map(e => ({ ...e, booking_id: 'next-guest', note: `Next guest private note ${e.id}` }))
    const nextBills = previous.pending_payments.map(item => ({ ...item, note: 'Edited by second operator' }))
    view.replace({ ...previous, revision: 9, state: { ...previous.state, employees: nextEmployees, pending: nextBills }, pending_payments: nextBills })
    await refreshBoard()
    assert.equal(field('Ghi chú hóa đơn').value, '')
    const preview = document.querySelector('[aria-label="Ghi chú booking"]').textContent
    assert.match(preview, /Nhẹ vai trái.*Không dùng dầu/)
    assert.doesNotMatch(preview, /Next guest/)
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes.length, 1)
    assert.equal(view.writes[0].expected_revision, 7)
    assert.equal(view.writes[0].payload.note, '')
    assert.equal(view.accepted.length, 0)
    assert.match(document.body.textContent, /đã thay đổi ở thiết bị khác/)
    assert.equal(field('Ghi chú hóa đơn').value, '')
    // A retry without reviewing must not silently advance to the newer source.
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes[1].expected_revision, 7)
    assert.equal(view.accepted.length, 0)
    await click(button('Hủy'))
    await click(button(source === 'group' ? 'Pay group' : 'Pay p1'))
    assert.equal(field('Ghi chú hóa đơn').value, source === 'group' ? 'Next guest private note e1\nNext guest private note e2' : 'Edited by second operator')
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes.at(-1).expected_revision, 9)
    assert.equal(view.accepted.length, 1)
  } finally { await view.dispose() }
})

test('quick sources use board revision while detailed pending sources use their own newer revision', async () => {
  const view = await pageFixture({ enforceCas: true, holdBoard: true, detailData: data => ({ ...data, revision: 9,
    pending_payments: data.pending_payments.map(item => ({ ...item, note: 'New detail note' })) }) })
  try {
    await click(button('Choose quick source'))
    await chooseSource('An, Bình')
    assert.equal(field('Ghi chú hóa đơn').value, pending.note, 'quick source came from board revision 7')
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes[0].expected_revision, 7)
    assert.equal(view.accepted.length, 0)
    await click(button('Hủy'))
    await click(button('Pay p1'))
    assert.equal(field('Ghi chú hóa đơn').value, 'New detail note')
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes[1].expected_revision, 9)
    assert.equal(view.accepted.length, 1)
  } finally { await view.dispose() }
})

test('explicit quick-source reselection refreshes its note and captured revision', async () => {
  const view = await pageFixture({ enforceCas: true })
  try {
    await click(button('Choose quick source'))
    await chooseSource('An, Bình')
    const previous = view.current()
    const nextBills = previous.pending_payments.map(item => ({ ...item, note: 'Changed at revision 9' }))
    view.replace({ ...previous, revision: 9, pending_payments: nextBills, state: { ...previous.state, pending: nextBills } })
    await refreshBoard()
    assert.equal(field('Ghi chú hóa đơn').value, pending.note)
    await chooseSource('An, Bình')
    assert.equal(field('Ghi chú hóa đơn').value, 'Changed at revision 9')
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes[0].expected_revision, 9)
    assert.equal(view.accepted.length, 1)
  } finally { await view.dispose() }
})

for (const operation of ['Lưu dịch vụ', 'Hoàn thành']) test(`${operation} rejects a stale booking draft after the same employee receives a different assignment`, async () => {
  const view = await pageFixture({ enforceCas: true, doing: true })
  try {
    await click(document.querySelector('.tour-table button[title="An"]'))
    await type(field('Ghi chú'), '')
    const previous = view.current()
    view.replace({ ...previous, revision: 9, state: { ...previous.state, employees: previous.state.employees.map(e => ({ ...e, booking_id: 'replacement', note: 'New customer booking', room: e.id === 'e1' ? '2.1' : e.room })) } })
    await refreshBoard()
    assert.equal(field('Ghi chú').value, '')
    await click(button(operation))
    assert.equal(view.writes[0].action, operation === 'Hoàn thành' ? 'finish_to_pending' : 'update_booking')
    assert.equal(view.writes[0].expected_revision, 7)
    assert.equal(view.writes[0].payload.note, '')
    assert.equal(view.writes[0].payload.room, '1.1')
    assert.equal(view.accepted.length, 0)
    assert.match(document.body.textContent, /đã thay đổi ở thiết bị khác/)
  } finally { await view.dispose() }
})

test('completed booking checkout forwards the completion revision after a later refresh', async () => {
  const view = await pageFixture({ enforceCas: true, doing: true, finishResult: true })
  try {
    await click(document.querySelector('.tour-table button[title="An"]'))
    await type(field('Ghi chú'), 'Completed note')
    await click(button('Hoàn thành'))
    assert.equal(view.writes[0].expected_revision, 7)
    assert.equal(field('Ghi chú hóa đơn').value, 'Completed note')
    view.replace({ ...view.current(), revision: 9 })
    await refreshBoard()
    await click(button('Thanh toán'))
    assert.equal(field('Ghi chú hóa đơn').value, 'Completed note')
    await click(button('Lưu thay đổi'))
    assert.equal(view.writes.at(-1).expected_revision, 8)
    assert.equal(view.accepted.length, 1, 'only Finish commits; stale checkout is rejected')
    assert.match(document.body.textContent, /đã thay đổi ở thiết bị khác/)
  } finally { await view.dispose() }
})
