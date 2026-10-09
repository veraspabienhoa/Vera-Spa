import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act, useState } from 'react'
import { JSDOM } from 'jsdom'
import { startSearchableDropdowns } from '../src/lib/searchableDropdowns.js'
import { formatVeraDate, parseVeraDate, formatVeraDateTime } from '../src/lib/veraDate.js'
import { multiBookingCombos } from '../src/lib/liveTourComboBooking.js'
import { orderedCatalog } from '../src/lib/serviceCatalog.js'
const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
async function component(name) {
  const built = await build({ entryPoints: [fileURLToPath(new URL(`../src/components/${name}.jsx`, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' } })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const SearchSelect = await component('LiveTourSearchSelect'), Clearable = await component('ClearableSearchInput')
const DateInput = await component('VeraDateInput'), DateTimeInput = await component('VeraDateTimeInput')
const PaymentSettings = await component('LiveTourPaymentSettings')
const BookingDialog = await component('LiveTourBookingDialog')
const type = (input, value) => act(() => {
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
  input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
})
async function render(Component) {
  const root = createRoot(document.querySelector('#root'))
  await act(() => root.render(React.createElement(Component)))
  return async () => act(() => root.unmount())
}

test('catalog order is stable for legacy/unranked rows and does not mutate cache data', () => {
  const catalog = [{ id: 'legacy' }, { id: 'third', display_order: 3 }, { id: 'first', display_order: '0' },
    { id: 'null', display_order: null }, { id: 'blank', display_order: '' }, { id: 'bool', display_order: false },
    { id: 'invalid', display_order: 'x' }, { id: 'tie', display_order: 3 }]
  const before = structuredClone(catalog)
  assert.deepEqual(orderedCatalog(catalog).map(item => item.id), ['first', 'third', 'tie', 'legacy', 'null', 'blank', 'bool', 'invalid'])
  assert.deepEqual(catalog, before)
})

for (const mode of ['single', 'multi']) test(`${mode} booking places 70 PR third according to settings`, async () => {
  const services = [
    { id: '90-pr', name: '90 PR Tiêu chuẩn', price: 300000, duration: 90, display_order: 0 },
    { id: '90', name: '90 Tiêu chuẩn', price: 250000, duration: 90, display_order: 1 },
    { id: '70', name: '70 Tiêu chuẩn', price: 200000, duration: 70, display_order: 3 },
    { id: 'room', name: 'Phòng riêng', price: 50000, duration: null, display_order: 4 },
    { id: '70-pr', name: '70 PR Tiêu chuẩn', price: 250000, duration: 70, private: true, display_order: 2 },
    { id: 'inactive', name: 'Ngừng bán', active: false, display_order: -1 },
  ]
  const before = structuredClone(services)
  const dispose = await render(() => React.createElement(BookingDialog, {
    data: { services, state: { employees: [], rooms: [] } }, context: mode === 'multi' ? { roomGroup: '1', roomLabel: '1' } : {},
    canBook: true, onClose() {}, onAction() {},
  }))
  try {
    const label = [...document.querySelectorAll('label')].find(node => node.textContent === (mode === 'multi' ? 'Dịch vụ *' : 'Dịch vụ'))
    const input = document.getElementById(label.htmlFor)
    await act(() => input.focus())
    const names = [...document.querySelectorAll('[role="listbox"] [role="option"] strong')].map(node => node.textContent)
    assert.deepEqual(names, ['90 PR Tiêu chuẩn', '90 Tiêu chuẩn', '70 PR Tiêu chuẩn', '70 Tiêu chuẩn', 'Phòng riêng'])
    await act(() => [...document.querySelectorAll('[role="option"]')].find(node => node.textContent.includes('70 PR Tiêu chuẩn')).click())
    assert.ok(document.body.textContent.includes('250.000 đ'))
    assert.deepEqual(services, before)
  } finally { await dispose() }
})

test('booking Clear closes, retains focus and allows intentional reopening by mouse or keyboard', async () => {
  let selected
  function Form() {
    const [value, set] = useState('r1'); selected = value
    return React.createElement(SearchSelect, { label: 'Phòng', value, options: [{ value: 'r1', label: '15.1' }], onChange: set })
  }
  const dispose = await render(Form)
  try {
    const input = document.querySelector('input')
    await act(() => document.querySelector('.search-clear-button').click())
    assert.equal(selected, '')
    assert.equal(input.value, '')
    assert.equal(document.activeElement, input)
    assert.equal(document.querySelector('[role="listbox"]'), null)
    await act(() => input.click())
    assert.ok(document.querySelector('[role="listbox"]'))
    await type(input, '15')
    const clear = document.querySelector('.search-clear-button')
    await act(() => { clear.focus(); clear.click() })
    assert.equal(document.querySelector('[role="listbox"]'), null)
    await act(() => input.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'ArrowDown', bubbles: true })))
    assert.ok(document.querySelector('[role="listbox"]'))
  } finally { await dispose() }
})

test('employee picker can filter keyed rows without crashing the React tree', async () => {
  const employees = [
    { value: 'Kieu Huong', label: 'Kiều Hương' },
    { value: 'Thuy Vy', label: 'Thúy Vy' },
    { value: 'Bao Tram', label: 'Bảo Trâm' },
  ]
  function Directory() {
    const [value, setValue] = useState('')
    const visible = value ? employees.filter((employee) => employee.value === value) : employees
    return React.createElement('main', { 'data-employee-directory': true },
      React.createElement(SearchSelect, {
        hideLabel: true,
        label: 'Tên nhân viên',
        value,
        options: employees,
        onChange: setValue,
      }),
      React.createElement('table', null, React.createElement('tbody', null,
        visible.map((employee) => React.createElement('tr', { key: employee.value }, React.createElement('td', null, employee.label))),
      )))
  }
  const dispose = await render(Directory)
  try {
    const input = document.querySelector('[data-employee-directory] input')
    await act(() => input.focus())
    await type(input, 'thuy vy')
    const option = [...document.querySelectorAll('[role="option"]')].find((row) => row.textContent.includes('Thúy Vy'))
    assert.ok(option)
    await act(() => option.click())
    assert.ok(document.querySelector('[data-employee-directory]'))
    assert.deepEqual([...document.querySelectorAll('tbody td')].map((cell) => cell.textContent), ['Thúy Vy'])
    assert.equal(document.querySelector('[role="listbox"]'), null)
  } finally { await dispose() }
})

test('datalist Clear closes shared menu and updates React filter', async () => {
  let value
  function Form() {
    const [text, set] = useState('An'); value = text
    return React.createElement(React.Fragment, null,
      React.createElement(Clearable, { value: text, list: 'staff', onChange: e => set(e.target.value) }),
      React.createElement('datalist', { id: 'staff' }, React.createElement('option', { value: 'An' })))
  }
  const stop = startSearchableDropdowns(document), dispose = await render(Form)
  try {
    await act(() => document.querySelector('input').focus())
    assert.ok(document.querySelector('.vera-searchable-dropdown'))
    await act(() => document.querySelector('.search-clear-button').click())
    assert.equal(value, '')
    assert.equal(document.querySelector('.vera-searchable-dropdown'), null)
  } finally { stop(); await dispose() }
})

test('dates pad day/month, validate leap years, and timestamps use Vietnam midnight', () => {
  assert.equal(formatVeraDate('2026-01-02'), '02-01-2026')
  assert.equal(formatVeraDate('2/1/2026'), '02-01-2026')
  assert.equal(parseVeraDate('29-02-2024'), '2024-02-29')
  assert.equal(parseVeraDate('29-02-2026'), '')
  assert.equal(formatVeraDate('2026-02-31'), '')
  assert.equal(parseVeraDate('01-02-26'), '')
  assert.equal(formatVeraDateTime('2026-01-02T18:04:05Z'), '03-01-2026 01:04:05')
  assert.equal(formatVeraDateTime('2026-01-02T18:04:05'), '02-01-2026 18:04:05')
  assert.equal(formatVeraDateTime('2/1/2026 18:04:05'), '02-01-2026 18:04:05')
  assert.equal(formatVeraDateTime('invalid'), '—')
})

test('incomplete/invalid date edits block submit; valid input and picker retain ISO API value', async () => {
  let stored
  function Form() {
    const [value, set] = useState('2026-01-02'); stored = value
    return React.createElement('form', null, React.createElement(DateInput, { value, min: '2026-01-01', max: '2026-12-31', required: true, onChange: e => set(e.target.value) }))
  }
  const dispose = await render(Form)
  try {
    const input = document.querySelector('input[type="text"]'), form = document.querySelector('form')
    assert.equal(input.value, '02-01-2026')
    for (const invalid of ['0301', '31022026', '03012027']) {
      await type(input, invalid)
      assert.equal(form.checkValidity(), false)
      assert.equal(stored, '2026-01-02')
    }
    await type(input, '03012026')
    assert.equal(input.value, '03-01-2026')
    assert.equal(stored, '2026-01-03')
    assert.equal(form.checkValidity(), true)
    await act(() => document.querySelector('.vera-date-picker-button').click())
    await type(document.querySelector('input[type="date"]'), '2026-02-04')
    assert.equal(input.value, '04-02-2026')
    assert.equal(stored, '2026-02-04')
  } finally { await dispose() }
})

test('date picker falls back to a native click when mobile Safari rejects showPicker', async () => {
  const dispose = await render(() => React.createElement(DateInput, { value: '2026-09-14', onChange: () => {} }))
  const original = dom.window.HTMLInputElement.prototype.showPicker
  let nativeClicks = 0
  dom.window.HTMLInputElement.prototype.showPicker = function () {
    this.addEventListener('click', () => nativeClicks++, { once: true })
    throw new dom.window.DOMException('Not allowed', 'NotAllowedError')
  }
  try {
    await act(() => document.querySelector('.vera-date-picker-button').click())
    const native = document.querySelector('input[type="date"]')
    assert.equal(nativeClicks, 1)
    assert.equal(native.getAttribute('aria-hidden'), null)
  } finally {
    if (original) dom.window.HTMLInputElement.prototype.showPicker = original
    else delete dom.window.HTMLInputElement.prototype.showPicker
    await dispose()
  }
})

test('invoice datetime retains ISO local payload and blocks partial dates', async () => {
  let stored
  function Form() {
    const [value, set] = useState('2026-01-02T15:45'); stored = value
    return React.createElement('form', null, React.createElement(DateTimeInput, { value, required: true, onChange: e => set(e.target.value) }))
  }
  const dispose = await render(Form)
  try {
    const date = document.querySelector('input[type="text"]'), time = document.querySelector('input[type="time"]')
    assert.equal(date.value, '02-01-2026')
    assert.equal(time.value, '15:45')
    await type(date, '03012026'); await type(time, '16:30')
    assert.equal(stored, '2026-01-03T16:30')
    await type(date, '03-01-202')
    assert.equal(document.querySelector('form').checkValidity(), false)
  } finally { await dispose() }
})

test('admin can submit a custom booking threshold alongside existing settings', async () => {
  let payload
  const dispose = await render(() => React.createElement(PaymentSettings, { value: { auto_print: false, tip_cards: [] }, onSave: value => { payload = value } }))
  try {
    const label = [...document.querySelectorAll('label')].find(label => label.textContent.includes('Hiện nhân viên'))
    assert.equal(label.querySelector('input').value, '30')
    await type(label.querySelector('input'), '45')
    await act(() => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
    assert.equal(payload.booking_available_minutes, 45)
    assert.deepEqual(payload.tip_cards, [])
  } finally { await dispose() }
})

test('single and room booking keep full-board STT when opening and searching idle employees', async () => {
  const BookingDialog = await component('LiveTourBookingDialog')
  const names = ['Bích Nhu', 'Cẩm Nhung', 'Tường San', 'Ngọc Nhung']
  const employees = names.map((name, index) => ({ id: `e${index}`, name, service: '', status: '', work_status: 'Đi làm', shift: 'Ca 1', sort_index: index }))
  const data = {
    state: { employees, rooms: [{ name: '2.1', active: true }] }, services: [],
    records: employees.map((row, index) => ({ _employee_id: row.id, STT: [18, 12, 1, 6][index] })),
  }
  for (const context of [{}, { roomGroup: '2' }]) {
    const dispose = await render(() => React.createElement(BookingDialog, { data, context, canBook: true, onClose() {} }))
    try {
      // Let the dialog's initial focus frame settle before opening suggestions.
      await act(async () => { await new Promise(resolve => window.requestAnimationFrame(resolve)) })
      const input = document.querySelector('input[role="combobox"]')
      await act(() => input.focus())
      const labels = () => [...document.querySelectorAll('[role="option"] .tour-select-option-heading > strong')].map(item => item.textContent)
      assert.deepEqual(labels(), ['Tường San', 'Ngọc Nhung', 'Cẩm Nhung', 'Bích Nhu'])
      await type(input, 'Nhung')
      assert.deepEqual(labels(), ['Ngọc Nhung', 'Cẩm Nhung'])
      await act(() => document.querySelector('[role="option"]').click())
      assert.equal(input.value, 'Ngọc Nhung')
      assert.equal(document.getElementById(input.getAttribute('aria-controls')), null)
    } finally { await dispose() }
  }
})

test('new room-booking rows copy the first service once and remain independently editable', async () => {
  const BookingDialog = await component('LiveTourBookingDialog')
  const data = {
    state: {
      employees: [
        { id: 'e1', name: 'Mỹ Duyên', service: '', status: '', work_status: 'Đi làm', shift: 'Ca 1' },
        { id: 'e2', name: 'Bảo Trâm', service: '', status: '', work_status: 'Đi làm', shift: 'Ca 1' },
      ],
      rooms: [{ name: '2.1', active: true }, { name: '2.2', active: true }],
    },
    services: [{ id: 'body-90', name: '90 Tiêu chuẩn', duration: 90, price: 250000 }],
    records: [],
  }
  const dispose = await render(() => React.createElement(BookingDialog, {
    data, context: { roomGroup: '2', roomLabel: 'Phòng 2' }, canBook: true, onClose() {},
  }))
  try {
    const serviceInput = () => {
      const label = [...document.querySelectorAll('label')].find(item => item.textContent === 'Dịch vụ *')
      return document.getElementById(label.htmlFor)
    }
    await act(async () => {
      serviceInput().focus()
      await new Promise(resolve => window.requestAnimationFrame(resolve))
    })
    assert.equal(document.activeElement, serviceInput())
    await act(() => document.querySelector('[role="option"]').click())
    assert.equal(serviceInput().value, '90 Tiêu chuẩn')
    await act(() => document.querySelector('.tour-multi-add').click())
    let serviceInputs = [...document.querySelectorAll('.tour-multi-booking-row')].map(row => {
      const label = [...row.querySelectorAll('label')].find(item => item.textContent === 'Dịch vụ *')
      return document.getElementById(label.htmlFor)
    })
    assert.deepEqual(serviceInputs.map(input => input.value), ['90 Tiêu chuẩn', '90 Tiêu chuẩn'])
    const secondService = serviceInputs[1].closest('.live-tour-search-select')
    await act(() => secondService.querySelector('.search-clear-button').click())
    serviceInputs = [...document.querySelectorAll('.tour-multi-booking-row')].map(row => {
      const label = [...row.querySelectorAll('label')].find(item => item.textContent === 'Dịch vụ *')
      return document.getElementById(label.htmlFor)
    })
    assert.deepEqual(serviceInputs.map(input => input.value), ['90 Tiêu chuẩn', ''])
  } finally { await dispose() }
})

function comboRoomFixture(remaining = 2) {
  return {
    state: { employees: [1, 2].map(id => ({ id: `e${id}`, name: `Test Worker ${id}`, work_status: 'Đi làm', shift: 'Ca 1' })),
      rooms: [{ name: '2.1', active: true }, { name: '2.2', active: true }] },
    services: [{ id: 'body', name: 'Test Body 90', duration: 90, price: 250000 }], records: [],
    customers: [{ id: 'c1', name: 'Test Customer', phone: '0900000001', combo_purchases: [{
      id: 'p1', combo_name: 'Test Combo', remaining: 5, booking_remaining: remaining,
      component_balances: [{ service_id: 'body', remaining: 5, booking_remaining: remaining }],
    }] }],
  }
}
const field = (scope, label) => document.getElementById([...scope.querySelectorAll('label')].find(item => item.textContent === label).htmlFor)
async function choose(scope, label, text) {
  await act(() => field(scope, label).focus())
  const option = [...document.querySelectorAll('[role="option"]')].find(item => item.textContent.includes(text))
  assert.ok(option, `Missing option ${text}`)
  await act(() => option.click())
}

test('room booking autofills combo services, aggregates guests and blocks shortage before sending', async () => {
  const BookingDialog = await component('LiveTourBookingDialog')
  const calls = []; let updateData, selectedIds
  const selected = ids => { selectedIds = ids }
  function Screen() {
    const [data, setData] = useState(comboRoomFixture()); updateData = setData
    return React.createElement(BookingDialog, { data, context: { roomGroup: '2', roomLabel: 'Phòng 2' },
      canBook: true, canCustomers: true, onClose() {}, onSelectedCustomersChange: selected,
      onAction: async (...args) => { calls.push(args); return {} } })
  }
  const dispose = await render(Screen)
  const rows = () => [...document.querySelectorAll('.tour-multi-booking-row')]
  try {
    await act(async () => { await new Promise(resolve => window.requestAnimationFrame(resolve)) })
    await choose(rows()[0], 'Khách hàng / chủ combo', 'Test Customer')
    assert.equal(field(rows()[0], 'Dịch vụ *').value, 'Test Body 90')
    assert.deepEqual(selectedIds, ['c1'])
    await act(() => [...document.querySelectorAll('label')].find(label => label.textContent.includes('Dùng combo của khách dòng 1')).querySelector('input').click())
    await act(() => document.querySelector('.tour-multi-add').click())
    assert.equal(field(rows()[1], 'Dịch vụ *').value, 'Test Body 90')
    assert.equal(field(rows()[1], 'Khách hàng / chủ combo').disabled, true)
    assert.match(document.querySelector('.tour-multi-combo-summary').textContent, /dùng 2 vé · sau booking còn 0 vé/)
    await choose(rows()[0], 'Nhân viên *', 'Test Worker 1')
    await choose(rows()[1], 'Nhân viên *', 'Test Worker 2')
    await act(() => updateData(comboRoomFixture(1)))
    assert.match(document.querySelector('[role="alert"]').textContent, /chỉ còn 1/)
    assert.equal(document.querySelector('button[type="submit"]').disabled, true)
    await act(() => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
    assert.equal(calls.length, 0)
    await act(() => updateData(comboRoomFixture(2)))
    await act(() => document.querySelector('form').dispatchEvent(new dom.window.Event('submit', { bubbles: true, cancelable: true })))
    assert.equal(calls.length, 1)
    assert.equal(calls[0][0], 'multi_booking')
    const bookings = calls[0][1].bookings
    assert.deepEqual(bookings.map(row => [row.customer_id, row.combo_purchase_id, row.service_items]), [
      ['c1', 'p1', [{ service_id: 'body', quantity: 1 }]], ['c1', 'p1', [{ service_id: 'body', quantity: 1 }]],
    ])
    assert.deepEqual(bookings.map(row => row.room), ['2.1', '2.2'])
  } finally { await dispose() }
})

test('single booking displays the auto-selected combo service and rejects excess quantity immediately', async () => {
  const BookingDialog = await component('LiveTourBookingDialog')
  const dispose = await render(() => React.createElement(BookingDialog, { data: comboRoomFixture(1),
    context: { employeeId: 'e1' }, canBook: true, canCustomers: true, onClose() {} }))
  try {
    await act(async () => { await new Promise(resolve => window.requestAnimationFrame(resolve)) })
    await choose(document, 'Khách hàng', 'Test Customer')
    assert.equal(document.querySelector('.tour-booking-service-picker input[readonly]').value, 'Test Body 90')
    assert.match(document.querySelector('.tour-customer-ticket-count').textContent, /Có thể đặt 1 vé/)
    await type(document.querySelector('.tour-booking-item input'), '2')
    assert.match(document.querySelector('[role="alert"]').textContent, /chỉ còn 1/)
    assert.equal(document.querySelector('button[type="submit"]').disabled, true)
  } finally { await dispose() }
})

test('draft ticket checks aggregate per owner and component even without the shared-combo switch', () => {
  const data = comboRoomFixture(1)
  const row = { customer_id: 'c1', combo_purchase_id: 'p1', service_id: 'body' }
  assert.match(multiBookingCombos([row, row], data.customers, data.services)[0].error, /chỉ còn 1/)
  const customers = [...data.customers, { ...data.customers[0], id: 'c2' }]
  const groups = multiBookingCombos([row, { ...row, customer_id: 'c2' }], customers, data.services)
  assert.equal(groups.length, 2)
  assert.ok(groups.every(group => !group.error && group.remaining === 0))
  assert.match(multiBookingCombos([row], [], data.services)[0].error, /thiếu dữ liệu/)
})

test('filter date clears on click without loading and keeps partial typing', async () => {
  const changes = []
  function Filter() {
    const [value, set] = useState('2026-09-03')
    return React.createElement('div', { className: 'live-tour-filters' }, React.createElement(DateInput, {
      value, onChange: e => { changes.push(e.target.value); set(e.target.value) },
    }))
  }
  const dispose = await render(Filter)
  try {
    const input = document.querySelector('input[type="text"]')
    await act(() => { input.focus(); input.click() })
    assert.equal(input.value, '')
    assert.deepEqual(changes, [])
    await type(input, '0410')
    await act(() => input.click())
    assert.equal(input.value, '04-10')
    assert.equal(input.checkValidity(), false)
    await type(input, '04102026')
    assert.equal(input.value, '04-10-2026')
    assert.deepEqual(changes, ['2026-10-04'])
    await act(() => input.click())
    assert.equal(input.value, '')
    await act(() => input.blur())
    assert.equal(changes.at(-1), '')
  } finally { await dispose() }
})

test('form dates and readonly filter dates retain their value on click', async () => {
  for (const props of [{}, { readOnly: true, clearOnFocus: true }, { clearOnFocus: false }]) {
    const dispose = await render(() => React.createElement(DateInput, { value: '2026-09-03', ...props }))
    try {
      const input = document.querySelector('input[type="text"]')
      await act(() => { input.focus(); input.click() })
      assert.equal(input.value, '03-09-2026')
    } finally { await dispose() }
  }
})
