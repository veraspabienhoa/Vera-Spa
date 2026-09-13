import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act, useState } from 'react'
import { JSDOM } from 'jsdom'
import { startSearchableDropdowns } from '../src/lib/searchableDropdowns.js'
import { formatVeraDate, parseVeraDate, formatVeraDateTime } from '../src/lib/veraDate.js'
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
const type = (input, value) => act(() => {
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
  input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
})
async function render(Component) {
  const root = createRoot(document.querySelector('#root'))
  await act(() => root.render(React.createElement(Component)))
  return async () => act(() => root.unmount())
}

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
  assert.equal(formatVeraDate('2026-01-02'), '02/01/2026')
  assert.equal(formatVeraDate('2/1/2026'), '02/01/2026')
  assert.equal(parseVeraDate('29/02/2024'), '2024-02-29')
  assert.equal(parseVeraDate('29/02/2026'), '')
  assert.equal(formatVeraDate('2026-02-31'), '')
  assert.equal(parseVeraDate('01/02/26'), '')
  assert.equal(formatVeraDateTime('2026-01-02T18:04:05Z'), '03/01/2026 01:04:05')
  assert.equal(formatVeraDateTime('2026-01-02T18:04:05'), '02/01/2026 18:04:05')
  assert.equal(formatVeraDateTime('2/1/2026 18:04:05'), '02/01/2026 18:04:05')
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
    assert.equal(input.value, '02/01/2026')
    for (const invalid of ['0301', '31022026', '03012027']) {
      await type(input, invalid)
      assert.equal(form.checkValidity(), false)
      assert.equal(stored, '2026-01-02')
    }
    await type(input, '03012026')
    assert.equal(input.value, '03/01/2026')
    assert.equal(stored, '2026-01-03')
    assert.equal(form.checkValidity(), true)
    await type(document.querySelector('input[type="date"]'), '2026-02-04')
    assert.equal(input.value, '04/02/2026')
    assert.equal(stored, '2026-02-04')
  } finally { await dispose() }
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
    assert.equal(date.value, '02/01/2026')
    assert.equal(time.value, '15:45')
    await type(date, '03012026'); await type(time, '16:30')
    assert.equal(stored, '2026-01-03T16:30')
    await type(date, '03/01/202')
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
