import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { defaultTourMonthFilters, defaultTourYesterdayFilters, EMPTY_TOUR_FILTERS, filterTourRows, tourFilterOptions } from '../src/lib/liveTourFilters.js'
import { summarizeEmployeeRevenue } from '../src/lib/liveTourEmployeeRevenue.js'
import { selectReportRows } from '../src/lib/liveTourReportSelection.js'
const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const built = await build({ entryPoints: [fileURLToPath(new URL('../src/components/LiveTourFilters.jsx', import.meta.url))], bundle: true, write: false,
  platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime', 'react-dom'], loader: { '.css': 'empty' } })
const module = { exports: {} }
new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
const rows = [
  { id: 'a', customer_name: 'Khách Đào', customer_phone: '0901234567', entries: [{ employee_name: 'Mỹ Duyên', service: 'Body 90' }, { employee_name: 'An An', service: 'Foot 60' }] },
  { id: 'b', customer_name: 'Khách Bình', entries: [{ employee_name: 'An An', service: 'Body 90' }] },
]
test('report selection reads only the visible collection and preserves invoice date semantics', () => {
  const reports = [
    { id: 'midnight', effective_at: '2026-09-04T17:00:00Z', business_date: '2026-09-04', total: 0 },
    { id: 'before', effective_at: '2026-09-04T16:59:59Z', total: 100 },
    { id: 'legacy', business_date: '05/09/2026', tip: 50, combo_sale: true },
  ]
  const data = { reports, get invoices() { throw Error('hidden invoices scanned') }, get performance() { throw Error('hidden performance scanned') } }
  const filters = { date_from: '2026-09-05', date_to: '2026-09-05' }
  assert.deepEqual(selectReportRows(data, 'revenue', filters).map(row => row.id), ['midnight', 'legacy'])
  assert.deepEqual(selectReportRows(data, 'tip', filters).map(row => row.id), ['legacy'])
  assert.deepEqual(selectReportRows(data, 'combos', filters).map(row => row.id), ['legacy'])
  assert.deepEqual(selectReportRows(data, 'history', filters), [])
  const untimed = [{ get effective_at() { throw Error('date parsed without date filter') } }]
  assert.equal(filterTourRows(untimed, {}).length, 1)
})
test('reports can start with the current Vietnam month selected', () => {
  assert.deepEqual(defaultTourMonthFilters(new Date('2026-09-13T05:00:00Z')), {
    ...EMPTY_TOUR_FILTERS, preset: 'month', date_from: '2026-09-01', date_to: '2026-09-30',
  })
})
test('reports default to yesterday in Vietnam time', () => {
  assert.deepEqual(defaultTourYesterdayFilters(new Date('2026-09-13T05:00:00Z')), {
    ...EMPTY_TOUR_FILTERS, preset: 'yesterday', date_from: '2026-09-12', date_to: '2026-09-12',
  })
})

test('employee report totals aggregate service money and TIP by filtered report rows', () => {
  assert.deepEqual(summarizeEmployeeRevenue([
    { employee_name: 'An An', total: 550000, tip: 50000 },
    { employee_name: 'An An', request: 'YC', total: 220000, tip: 20000 },
    { employee_name: 'Mỹ Duyên', total: 300000, tip: 0 },
  ]), [
    { employee: 'An An', service: 700000, tip: 70000, total: 770000, tourRows: 1, requestRows: 1, rows: 2 },
    { employee: 'Mỹ Duyên', service: 300000, tip: 0, total: 300000, tourRows: 1, requestRows: 0, rows: 1 },
  ])
})
test('suggestions include all invoice entries and report rows without duplicates', () => {
  const options = tourFilterOptions([...rows, { employee_name: 'Thúy Vy', customer_name: 'Khách Đào', service: 'Facial' }])
  assert.equal(options.employee.length, 3)
  assert.equal(options.customer.length, 3)
  assert.equal(options.service.length, 3)
  assert.deepEqual(tourFilterOptions(), { employee: [], customer: [], service: [], bill_no: [] })
  assert.deepEqual(filterTourRows(rows, { employee: 'my duyen', service: 'foot' }), [])
})
test('typing, choosing, clearing and switching lists update searches immediately', async () => {
  const root = createRoot(document.querySelector('#root'))
  let current = { ...EMPTY_TOUR_FILTERS }, source = rows
  const render = () => root.render(React.createElement(module.exports.default, { rows: source, value: current, onChange(value) { current = value; render() } }))
  const input = label => document.getElementById([...document.querySelectorAll('label')].find(x => x.textContent === label).htmlFor)
  const type = async (field, value) => act(() => {
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(field, value)
    field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
  try {
    await act(render)
    const employee = input('Nhân viên')
    await act(() => employee.focus())
    assert.equal(document.querySelectorAll('[role=option]').length, 3)
    await type(employee, 'my duyen')
    assert.deepEqual(filterTourRows(rows, current).map(x => x.id), ['a'])
    await act(() => [...document.querySelectorAll('[role=option]')].find(x => x.textContent === 'Mỹ Duyên').click())
    assert.equal(employee.value, 'Mỹ Duyên')
    assert.equal(employee.getAttribute('aria-expanded'), 'false')
    await act(() => input('Dịch vụ').focus())
    await type(input('Dịch vụ'), 'Foot')
    assert.equal(filterTourRows(rows, current).length, 0)
    await act(() => document.querySelector('.live-tour-filters-reset').click())
    assert.equal(current.employee, 'Mỹ Duyên')
    assert.equal(current.customer, '')
    assert.equal(current.service, 'Foot')
    assert.equal(current.preset, 'all')
    current = { ...EMPTY_TOUR_FILTERS }
    await act(render)
    await act(() => input('Khách hàng').focus())
    await act(() => [...document.querySelectorAll('[role=option]')].find(x => x.textContent === 'Khách Đào - 0901234567').click())
    assert.deepEqual(filterTourRows(rows, current).map(x => x.id), ['a'])
    await type(input('Khách hàng'), '090 123 4567')
    assert.equal(filterTourRows(rows, current).length, 1)
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(x => x.textContent), ['Tất cả', 'Khách Đào - 0901234567'])
    await act(() => input('Khách hàng').closest('.clearable-search-input').querySelector('button').click())
    assert.equal(current.customer, '')
    assert.equal(input('Khách hàng').value, '')
    source = [{ employee_name: 'Thúy Vy', service: 'Facial', customer_name: 'Khách Mới' }]
    await act(render)
    await act(() => document.querySelector('.live-tour-filters-reset').click())
    await act(() => input('Nhân viên').focus())
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(x => x.textContent), ['Tất cả', 'Thúy Vy'])
  } finally { await act(() => root.unmount()) }
})
test('customer and service catalogs remain searchable when the active panel has no rows', async () => {
  const root = createRoot(document.querySelector('#root'))
  let current = { ...EMPTY_TOUR_FILTERS }
  const props = {
    rows: [],
    customers: [{ id: 'c1', name: 'Anh Lưu', phone: '0919442626', combo_purchases: [{remaining: 3, booking_remaining: 1}, {remaining: 4}] }],
    services: [{ id: 's1', name: '90 Tiêu chuẩn' }],
    value: current,
    onChange(value) { current = value },
  }
  const input = label => document.getElementById([...document.querySelectorAll('label')].find(x => x.textContent === label).htmlFor)
  try {
    await act(() => root.render(React.createElement(module.exports.default, props)))
    await act(() => input('Khách hàng').focus())
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(x => x.textContent), ['Tất cả', 'Anh Lưu - 0919442626Có thể đặt 5 vé combo'])
    await act(() => input('Dịch vụ').focus())
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(x => x.textContent), ['Tất cả', '90 Tiêu chuẩn'])
  } finally { await act(() => root.unmount()) }
})
test.after(() => dom.window.close())

test('employee replacement follows the server remaining-time decision', async () => {
  const { canChangeEmployee } = await import('../src/lib/liveTourEmployeeChange.js')
  const row = { _tour_groups: ['doing'], _employee_change_allowed: true }
  assert.equal(canChangeEmployee(row), true)
  assert.equal(canChangeEmployee({ ...row, _tour_groups: ['waiting'] }), false)
  assert.equal(canChangeEmployee({ ...row, _employee_change_allowed: false }), false)
})

test('total amount matches displayed revenue including zero and combines with other filters', () => {
  const source=[{id:'a',total:250000,employee_name:'An'},{id:'b',total:250000,employee_name:'Bình'},{id:'c',total:0,employee_name:'An'}]
  assert.deepEqual(filterTourRows(source,{total_amount:'250.000',employee:'An'}).map(row=>row.id),['a'])
  assert.deepEqual(filterTourRows(source,{total_amount:0}).map(row=>row.id),['c'])
  assert.equal(filterTourRows(source,{total_amount:''}).length,3)
})

test('TIP money filter compares exact tip including zero independently from invoice total',()=>{
 const rows=[{id:'a',tip:50000,total_amount:250000},{id:'b',tip:150000,total_amount:250000},{id:'c',tip:0,total_amount:50000}]
 assert.deepEqual(filterTourRows(rows,{tip_amount:'50.000'}).map(row=>row.id),['a'])
 assert.deepEqual(filterTourRows(rows,{tip_amount:0}).map(row=>row.id),['c'])
 assert.equal(filterTourRows(rows,{tip_amount:''}).length,3)
})


test('date shortcuts have the requested order, preserve other filters and accept compact dates', async () => {
  const root = createRoot(document.querySelector('#root'))
  let current = { ...EMPTY_TOUR_FILTERS, employee: 'An An', date_from: '2026-09-01', date_to: '2026-09-30', preset: 'month' }
  const render = () => root.render(React.createElement(module.exports.default, { rows, value: current, onChange(value) { current = value; render() } }))
  const dateInput = () => document.querySelector('.report-date-preset input')
  const type = async value => act(() => {
    const field = dateInput()
    Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(field, value)
    field.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
  })
  const chooseDate = async text => {
    await act(() => dateInput().focus())
    await type(text)
    await act(() => dateInput().dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true })))
  }
  try {
    await act(render)
    const buttons = [...document.querySelectorAll('.report-date-buttons button')]
    const labels = ['Tất cả','Hôm nay','Hôm qua','Tuần này','Tuần trước','Tháng này','Tháng trước','Tùy chỉnh']
    assert.deepEqual(buttons.map(b => b.textContent), labels)
    await act(() => dateInput().focus())
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(b => b.textContent), labels)
    await act(() => buttons[7].click())
    assert.equal(current.preset, 'custom')
    assert.equal(current.date_from, '2026-09-01')
    assert.equal(current.date_to, '2026-09-30')
    for (const text of ['30092026','30-09-2026','30/09/2026']) {
      await chooseDate(text)
      assert.equal(current.date_from, '2026-09-30')
      assert.equal(current.date_to, '2026-09-30')
      assert.equal(current.employee, 'An An')
    }
    for (const invalid of ['31092026','29022025','3009','300920260']) {
      await chooseDate(invalid)
      assert.equal(current.date_from, '2026-09-30')
      assert.equal(document.querySelectorAll('[role=option]').length, 0)
    }
    await chooseDate('29022024')
    assert.equal(current.date_from, '2024-02-29')
    await act(() => [...document.querySelectorAll('.report-date-buttons button')][0].click())
    assert.equal(current.date_from, '')
    assert.equal(current.date_to, '')
    assert.equal(current.employee, 'An An')
  } finally { await act(() => root.unmount()) }
})

test('exact date uses Vietnam invoice business date and combines with other filters', () => {
  const source = [
    {id:'midnight',effective_at:'2026-09-30T17:15:00Z',bill_no:'10'},
    {id:'business',business_date:'2026-10-01',created_at:'2026-10-02T03:00:00Z',bill_no:'11'},
    {id:'before',effective_at:'2026-09-30T16:59:00Z',bill_no:'12'},
  ]
  assert.deepEqual(filterTourRows(source,{date:'2026-10-01'},true).map(r=>r.id),['midnight','business'])
  assert.deepEqual(filterTourRows(source,{date:'2026-10-01',bill_no:'11'},true).map(r=>r.id),['business'])
})
