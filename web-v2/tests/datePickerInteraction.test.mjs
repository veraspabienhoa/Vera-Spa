import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act, useState } from 'react'
import { JSDOM } from 'jsdom'

const dom = new JSDOM('<body><div id="root"></div><button id="outside">Outside</button></body>', { pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const built = await build({ entryPoints: [fileURLToPath(new URL('../src/components/VeraDateInput.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'] })
const module = { exports: {} }
new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), module, module.exports)
const DateInput = module.exports.default
const field = () => document.querySelector('input[type="text"]')
const picker = () => document.querySelector('input[type="date"]')
const type = (input, value) => act(() => {
  Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
  input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
})
async function mount(props = {}, filter = false) {
  const changes = [], validity = []
  let latestProps = props
  const root = createRoot(document.querySelector('#root'))
  function Form() {
    const [value, setValue] = useState('2026-10-10')
    return React.createElement('form', { className: filter ? 'live-tour-filters' : '' }, React.createElement(DateInput, {
      value, 'aria-label': 'Từ ngày', onChange: event => { changes.push(event.target.value); setValue(event.target.value) },
      onDraftValidity: valid => validity.push(valid), ...latestProps,
    }))
  }
  await act(() => root.render(React.createElement(Form)))
  return { changes, validity, rerender: next => act(() => { latestProps = next; root.render(React.createElement(Form)) }), dispose: () => act(() => root.unmount()) }
}

test('the actual native calendar hit target opens immediately with no filter callback', async () => {
  const fixture = await mount()
  const calls = []
  picker().showPicker = function () { calls.push(this) }
  try {
    for (let n = 0; n < 8; n++) await act(() => picker().click())
    assert.equal(calls.length, 8)
    assert.ok(calls.every(node => node === picker()))
    assert.deepEqual(fixture.changes, [])
    assert.equal(field().value, '10-10-2026')
  } finally { await fixture.dispose() }
})

test('moving from a focus-cleared filter to its calendar does not clear or reload the filter', async () => {
  const fixture = await mount({}, true)
  let opens = 0
  picker().showPicker = () => { opens++ }
  try {
    await act(() => field().focus())
    assert.equal(field().value, '')
    await act(() => { picker().focus(); picker().click() })
    assert.equal(opens, 1)
    assert.deepEqual(fixture.changes, [])
    assert.equal(field().value, '10-10-2026')
    assert.equal(field().checkValidity(), true)
    // Closing the native dialog without a change has no commit event.
    await act(() => document.querySelector('#outside').focus())
    assert.deepEqual(fixture.changes, [])
  } finally { await fixture.dispose() }
})

test('valid typing, blur and repeated calendar selection commit each changed ISO date once', async () => {
  const fixture = await mount()
  try {
    await act(() => field().focus())
    await type(field(), '11102026')
    await act(() => document.querySelector('#outside').focus())
    assert.deepEqual(fixture.changes, ['2026-10-11'])
    await type(picker(), '2026-10-12')
    await act(() => { field().focus(); field().blur() })
    assert.deepEqual(fixture.changes, ['2026-10-11', '2026-10-12'])
  } finally { await fixture.dispose() }
})

test('partial manual draft survives calendar cancel and still prevents stale form submission', async () => {
  const fixture = await mount({}, true)
  picker().showPicker = () => {}
  try {
    await act(() => field().focus())
    await type(field(), '1210')
    await act(() => { picker().focus(); picker().click() })
    assert.equal(field().value, '12-10')
    assert.equal(document.querySelector('form').checkValidity(), false)
    assert.deepEqual(fixture.changes, [])
    await type(picker(), '2026-10-12')
    assert.equal(field().value, '12-10-2026')
    assert.equal(document.querySelector('form').checkValidity(), true)
    assert.deepEqual(fixture.changes, ['2026-10-12'])
  } finally { await fixture.dispose() }
})

test('direct native fallback never recursively clicks when showPicker is unavailable or rejected', async () => {
  for (const supported of [false, true]) {
    const fixture = await mount()
    let clicks = 0
    const node = picker()
    if (supported) node.showPicker = () => { throw new dom.window.DOMException('Unavailable', 'NotAllowedError') }
    node.addEventListener('click', () => clicks++)
    try {
      await act(() => node.click())
      assert.equal(clicks, 1)
      assert.deepEqual(fixture.changes, [])
    } finally { await fixture.dispose() }
  }
})

test('a present but ineffective showPicker never cancels native pointer activation', async () => {
  const fixture = await mount()
  picker().showPicker = () => {}
  try {
    const event = new dom.window.MouseEvent('click', { bubbles: true, cancelable: true })
    await act(() => picker().dispatchEvent(event))
    assert.equal(event.defaultPrevented, false)
    assert.deepEqual(fixture.changes, [])
  } finally { await fixture.dispose() }
})

test('dragging away from the calendar cannot suppress the next intentional empty blur', async () => {
  const fixture = await mount({}, true)
  try {
    await act(() => {
      picker().focus()
      picker().dispatchEvent(new dom.window.Event('pointerdown', { bubbles: true }))
      document.querySelector('#outside').dispatchEvent(new dom.window.Event('pointerup', { bubbles: true }))
    })
    await act(() => field().focus())
    assert.equal(field().value, '')
    await act(() => document.querySelector('#outside').focus())
    assert.deepEqual(fixture.changes, [''])
  } finally { await fixture.dispose() }
})

test('calendar is keyboard reachable and Enter opens it without submitting the form', async () => {
  const fixture = await mount()
  let opens = 0
  picker().showPicker = () => { opens++ }
  try {
    assert.equal(picker().tabIndex, 0)
    const event = new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })
    await act(() => { picker().focus(); picker().dispatchEvent(event) })
    assert.equal(opens, 1)
    assert.equal(event.defaultPrevented, true)
    assert.deepEqual(fixture.changes, [])
  } finally { await fixture.dispose() }
})

test('keyboard activation keeps the direct native fallback when showPicker is unavailable', async () => {
  for (const supported of [false, true]) {
    const fixture = await mount()
    let clicks = 0
    const node = picker()
    if (supported) node.showPicker = () => { throw new dom.window.DOMException('Unavailable', 'NotAllowedError') }
    node.addEventListener('click', () => clicks++)
    try {
      await act(() => node.dispatchEvent(new dom.window.KeyboardEvent('keydown', { key: 'Enter', bubbles: true, cancelable: true })))
      assert.equal(clicks, 1)
      assert.deepEqual(fixture.changes, [])
    } finally { await fixture.dispose() }
  }
})

test('picker changes retain min/max validation, leap dates, intentional clearing and ISO values', async () => {
  const fixture = await mount({ min: '2024-02-01', max: '2026-12-31', clearable: true })
  try {
    await type(picker(), '2027-01-01')
    assert.deepEqual(fixture.changes, [])
    assert.equal(field().checkValidity(), false)
    await type(picker(), '2024-02-29')
    assert.deepEqual(fixture.changes, ['2024-02-29'])
    assert.equal(field().value, '29-02-2024')
    await act(() => document.querySelector('.vera-date-clear-button').click())
    await act(() => { field().focus(); field().blur() })
    assert.deepEqual(fixture.changes, ['2024-02-29', ''])
  } finally { await fixture.dispose() }
})

test('disabled and readonly controls never open a calendar or emit a value', async () => {
  for (const props of [{ disabled: true }, { readOnly: true }]) {
    const fixture = await mount(props)
    let opens = 0
    try {
      if (props.readOnly) assert.equal(picker(), null)
      else {
        picker().showPicker = () => { opens++ }
        await act(() => { picker().click(); document.querySelector('.vera-date-picker-button').click() })
      }
      assert.equal(opens, 0)
      assert.deepEqual(fixture.changes, [])
    } finally { await fixture.dispose() }
  }
})

test('a changed min/max constraint is revalidated on blur without resubmitting the date', async () => {
  const fixture = await mount({ clearOnFocus: false })
  try {
    await fixture.rerender({ clearOnFocus: false, min: '2026-10-11' })
    await act(() => { field().focus(); field().blur() })
    assert.equal(field().checkValidity(), false)
    assert.equal(fixture.validity.at(-1), false)
    assert.deepEqual(fixture.changes, [])
    await fixture.rerender({ clearOnFocus: false, min: '2026-10-09' })
    await act(() => { field().focus(); field().blur() })
    assert.equal(field().checkValidity(), true)
    assert.equal(fixture.validity.at(-1), true)
    assert.deepEqual(fixture.changes, ['2026-10-10'])
  } finally { await fixture.dispose() }
})

test('specialized native calendar hit widths match their visible icons', () => {
  const css = file => readFileSync(new URL(`../src/${file}`, import.meta.url), 'utf8')
  assert.match(css('styles.css'), /\.staff-table \.vera-date-input > \.vera-native-date-picker\s*\{\s*width:\s*27px\s*!important/)
  assert.match(css('clear-borders.css'), /\.online-booking-periods \.vera-native-date-picker\{width:36px!important\}/)
  assert.match(css('pages/DevicesAndCheckin.css'), /\.checkin-filter-details \.vera-date-input > \.vera-native-date-picker\s*\{\s*width:30px!important/)
  assert.match(css('styles.css'), /\.vera-native-date-picker::\-webkit-calendar-picker-indicator\s*\{[^}]*inset:\s*0;/)
})
