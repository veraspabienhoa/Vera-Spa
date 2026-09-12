import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { EMPTY_TOUR_FILTERS, filterTourRows, tourFilterOptions } from '../src/lib/liveTourFilters.js'
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
test('suggestions include all invoice entries and report rows without duplicates', () => {
  const options = tourFilterOptions([...rows, { employee_name: 'Thúy Vy', customer_name: 'Khách Đào', service: 'Facial' }])
  assert.equal(options.employee.length, 3)
  assert.equal(options.customer.length, 3)
  assert.equal(options.service.length, 3)
  assert.deepEqual(tourFilterOptions(), { employee: [], customer: [], service: [] })
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
    assert.equal(current.employee, '')
    assert.equal(current.customer, '')
    assert.equal(current.service, '')
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
    customers: [{ id: 'c1', name: 'Anh Lưu', phone: '0919442626', combo_purchases: [{remaining: 3}, {remaining: 4}] }],
    services: [{ id: 's1', name: '90 Tiêu chuẩn' }],
    value: current,
    onChange(value) { current = value },
  }
  const input = label => document.getElementById([...document.querySelectorAll('label')].find(x => x.textContent === label).htmlFor)
  try {
    await act(() => root.render(React.createElement(module.exports.default, props)))
    await act(() => input('Khách hàng').focus())
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(x => x.textContent), ['Tất cả', 'Anh Lưu - 0919442626Còn 7 vé combo'])
    await act(() => input('Dịch vụ').focus())
    assert.deepEqual([...document.querySelectorAll('[role=option]')].map(x => x.textContent), ['Tất cả', '90 Tiêu chuẩn'])
  } finally { await act(() => root.unmount()) }
})
test.after(() => dom.window.close())

test('employee replacement is available only in the original first ten minutes', async () => {
  const { canChangeEmployee } = await import('../src/lib/liveTourEmployeeChange.js')
  const start = Date.parse('2026-09-11T16:00:00+07:00')
  const row = { _tour_groups: ['doing'], _employee_change_started_at: new Date(start).toISOString(), _employee_change_until: new Date(start + 600000).toISOString() }
  assert.equal(canChangeEmployee(row, start), true)
  assert.equal(canChangeEmployee(row, start + 600000), true)
  assert.equal(canChangeEmployee(row, start + 600001), false)
  assert.equal(canChangeEmployee(row, start - 1), false)
  assert.equal(canChangeEmployee({ ...row, _tour_groups: ['waiting'] }, start), false)
  assert.equal(canChangeEmployee({ ...row, _employee_change_until: '' }, start), false)
})
