import assert from 'node:assert/strict'
import test from 'node:test'
import { JSDOM } from 'jsdom'
import React, { act } from 'react'
import { createRoot } from 'react-dom/client'
import { dropdownOptions, startSearchableDropdowns } from '../src/lib/searchableDropdowns.js'

function fixture(markup = '<label>Nhân viên<select><option value="">Tất cả</option><option value="dan">Linh Đan</option><option value="son">Lê Sơn</option></select></label>') {
  const dom = new JSDOM(`<body>${markup}</body>`, { pretendToBeVisual: true })
  const doc = dom.window.document
  const stop = startSearchableDropdowns(doc)
  const key = (target, value) => target.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: value, bubbles: true, cancelable: true }))
  const open = (select = doc.querySelector('select')) => { select.dispatchEvent(new dom.window.MouseEvent('pointerdown', { bubbles: true, cancelable: true })); return doc.querySelector('.vera-searchable-dropdown input') }
  const type = (input, value) => { input.value = value; input.dispatchEvent(new dom.window.Event('input', { bubbles: true })) }
  return { dom, doc, open, type, key, dispose: () => { stop(); dom.window.close() } }
}

test('Vietnamese search, option groups, disabled options, and every result remain available', () => {
  const f = fixture('<select><option value="0">Tất cả</option><optgroup label="Lễ tân" disabled><option value="1">Linh Đan</option></optgroup><option value="2" hidden>Ẩn</option>' + Array.from({ length: 150 }, (_, i) => `<option value="n${i}">Nhân viên ${i}</option>`).join('') + '</select>')
  try {
    assert.equal(dropdownOptions(f.doc.querySelector('select'), 'LE TAN')[0].disabled, true)
    const input = f.open()
    assert.equal(f.doc.querySelectorAll('[role="option"]').length, 152)
    f.type(input, 'nhan vien 149')
    assert.equal(f.doc.querySelector('[role="option"]').textContent, 'Nhân viên 149')
    f.key(input, 'Enter')
    assert.equal(f.doc.querySelector('select').value, 'n149')
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
  } finally { f.dispose() }
})

test('typing only filters; keyboard commit fires one change and empty option clears selection', () => {
  const f = fixture()
  try {
    const select = f.doc.querySelector('select')
    let changes = 0
    select.addEventListener('change', () => changes++)
    const input = f.open()
    f.type(input, 'linh dan')
    assert.equal(select.value, '')
    assert.equal(changes, 0)
    f.key(input, 'Enter')
    assert.equal(select.value, 'dan')
    assert.equal(changes, 1)
    const again = f.open()
    f.type(again, 'tat ca')
    f.doc.querySelector('[role="option"]').click()
    assert.equal(select.value, '')
    assert.equal(changes, 2)
  } finally { f.dispose() }
})

test('Escape cancels without closing parent dialog; arrows skip disabled and Tab returns to source', () => {
  const f = fixture('<select required><option value="">Chọn</option><option disabled value="x">Không được chọn</option><option value="s">Lê Sơn</option></select><button>Tiếp tục</button>')
  try {
    let dialogClosed = false
    f.doc.addEventListener('keydown', (e) => { if (e.key === 'Escape') dialogClosed = true })
    const select = f.doc.querySelector('select')
    let input = f.open()
    f.key(input, 'ArrowDown')
    assert.equal(f.doc.getElementById(input.getAttribute('aria-activedescendant')).textContent, 'Lê Sơn')
    f.key(input, 'Escape')
    assert.equal(dialogClosed, false)
    assert.equal(select.value, '')
    assert.equal(select.checkValidity(), false)
    input = f.open()
    f.key(input, 'Tab')
    assert.equal(f.doc.activeElement, select)
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
  } finally { f.dispose() }
})

test('dynamic controls, option refresh, disabled fieldsets and source removal are handled', async () => {
  const f = fixture('<div id="root"></div>')
  try {
    f.doc.querySelector('#root').innerHTML = '<fieldset disabled><select><option>Khóa</option></select></fieldset><select id="live"><option>A</option></select>'
    f.open(f.doc.querySelector('fieldset select'))
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
    const select = f.doc.querySelector('#live')
    f.open(select)
    select.add(new f.dom.window.Option('B', 'b'))
    await new Promise((resolve) => f.dom.window.setTimeout(resolve, 0))
    assert.equal(f.doc.querySelectorAll('[role="option"]').length, 2)
    select.remove()
    await new Promise((resolve) => f.dom.window.setTimeout(resolve, 0))
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
  } finally { f.dispose() }
})

test('typing a letter opens search; no results never submits or changes the native value', () => {
  const f = fixture()
  try {
    const select = f.doc.querySelector('select')
    f.key(select, 's')
    const input = f.doc.querySelector('.vera-searchable-dropdown input')
    assert.equal(input.value, 's')
    f.type(input, 'khong ton tai')
    assert.ok(f.doc.querySelector('[role="status"]'))
    f.key(input, 'Enter')
    assert.equal(select.value, '')
    assert.ok(f.doc.querySelector('.vera-searchable-dropdown'))
  } finally { f.dispose() }
})

test('React receives the new selection and safely removes keyed rows while the menu is open', async () => {
  const f = fixture('<div id="root"></div>')
  const before = Object.fromEntries(['window', 'document', 'IS_REACT_ACT_ENVIRONMENT'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  Object.defineProperties(globalThis, { window: { value: f.dom.window, configurable: true }, document: { value: f.doc, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true } })
  const root = createRoot(f.doc.querySelector('#root'))
  let picked = ''
  function App() {
    const [value, setValue] = React.useState('')
    const [visible, setVisible] = React.useState(true)
    return React.createElement('div', null,
      React.createElement('button', { onClick: () => setVisible(false) }, 'Hide'),
      visible && React.createElement('select', { key: 'employee', value, onChange: (event) => { picked = event.target.value; setValue(picked) } },
        React.createElement('option', { value: '' }, 'Tất cả'), React.createElement('option', { value: 'son' }, 'Lê Sơn')))
  }
  try {
    await act(() => root.render(React.createElement(App)))
    const input = f.open()
    f.type(input, 'le son')
    await act(() => f.key(input, 'Enter'))
    assert.equal(picked, 'son')
    assert.equal(f.doc.querySelector('select').value, 'son')
    f.open()
    await act(() => f.doc.querySelector('#root button').click())
    assert.equal(f.doc.querySelector('select'), null)
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
  } finally {
    await act(() => root.unmount())
    f.dispose()
    for (const [key, descriptor] of Object.entries(before)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] }
  }
})

test('An An does not match Vân Anh or duplicate fields, but accents and partial last words work', () => {
  const f = fixture('<select><option value="aa">An An</option><option value="va">Vân Anh</option><option value="An">An</option><option value="d">Đặng Ánh</option></select>')
  try {
    const input = f.open()
    f.type(input, 'an an')
    assert.deepEqual([...f.doc.querySelectorAll('[role="option"]')].map((r) => r.textContent), ['An An'])
    f.type(input, 'dang a')
    assert.deepEqual([...f.doc.querySelectorAll('[role="option"]')].map((r) => r.textContent), ['Đặng Ánh'])
  } finally { f.dispose() }
})

test('filtering keeps popup geometry stable and never scrolls the page', () => {
  const f = fixture()
  try {
    const select = f.doc.querySelector('select')
    select.getBoundingClientRect = () => ({ top: 610, bottom: 654, left: 10, width: 300 })
    f.dom.window.HTMLElement.prototype.scrollIntoView = () => { throw Error('Must not scroll page') }
    const input = f.open()
    const menu = f.doc.querySelector('.vera-searchable-dropdown')
    const before = [menu.style.top, menu.style.left, menu.style.height]
    f.type(input, 'son')
    assert.deepEqual([menu.style.top, menu.style.left, menu.style.height], before)
    f.type(input, 'no results')
    assert.deepEqual([menu.style.top, menu.style.left, menu.style.height], before)
    assert.equal(f.dom.window.scrollY, 0)
  } finally { f.dispose() }
})

test('datalist fields use the same accurate results and preserve free typing', () => {
  const f = fixture('<label>Nhân viên<input list="names" /></label><datalist id="names"><option value="An An"/><option value="Vân Anh"/></datalist>')
  try {
    const input = f.doc.querySelector('input')
    let changes = 0
    input.addEventListener('change', () => changes++)
    input.focus()
    assert.equal(input.hasAttribute('list'), false)
    f.type(input, 'an an')
    assert.deepEqual([...f.doc.querySelectorAll('[role="option"]')].map((r) => r.textContent), ['An An'])
    assert.equal(changes, 0)
    f.key(input, 'Enter')
    assert.equal(input.value, 'An An')
    assert.equal(input.getAttribute('list'), 'names')
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
    assert.equal(changes, 1)
    f.open(input)
    f.type(input, 'tên mới')
    f.key(input, 'Escape')
    assert.equal(input.value, 'tên mới')
    assert.equal(input.getAttribute('list'), 'names')
    assert.equal(f.doc.querySelector('.vera-searchable-dropdown'), null)
  } finally { f.dispose() }
})

test('customer and invoice search preserve phone formatting without partial-word name matches', async () => {
  const { customerMatches } = await import('../src/lib/customerSearch.js')
  const { filterTourRows } = await import('../src/lib/liveTourFilters.js')
  assert.equal(customerMatches({ name: 'Vân Anh', phone: '0912345678' }, 'an an'), false)
  assert.equal(customerMatches({ name: 'An', phone: '0912345678' }, 'an an'), false)
  assert.equal(customerMatches({ name: 'An An', phone: '+84 912 345 678' }, 'an an 0912 345 678'), true)
  assert.equal(customerMatches({ name: 'An An', phone: '0912345678' }, '345 678'), true)
  const rows = ['An An', 'Vân Anh'].map((name) => ({ entries: [{ employee_name: name, service: 'Body 90 phút' }] }))
  assert.equal(filterTourRows(rows, { employee: 'An An' }).length, 1)
  assert.equal(filterTourRows(rows, { employee: 'an an', service: 'body 90' }).length, 1)
})
