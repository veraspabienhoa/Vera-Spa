import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

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
  external: ['react', 'react/jsx-runtime', 'lucide-react'], loader: { '.css': 'empty' },
  plugins: [{ name: 'mock-boundaries', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi = globalThis.__tourTestApi;', loader: 'js' }))
    b.onResolve({ filter: /^\.\.\/components\// }, (args) => /LiveTour(AppointmentInput|ServiceActions)$/.test(args.path) ? undefined : ({ path: args.path, namespace: 'dialog' }))
    b.onLoad({ filter: /.*/, namespace: 'dialog' }, () => ({ contents: 'export default function Dialog(){return null}', loader: 'js' }))
  } }],
})

async function fixture({ canEdit = true, conflict = false, payable = false } = {}) {
  dom.window.localStorage.clear()
  const records = ['An An', 'An Bình'].map((name, i) => ({ _id: `e${i + 1}`, 'Tên nhân viên': name, 'STT': i + 1,
    'Lịch hẹn': i ? '' : '16:00', 'Vào ca': 'Ca 1', 'Trạng thái': '', 'Dịch vụ': '', 'Phòng': '',
    _tour_groups: ['working', 'available'], _payment_pending: payable && !i }))
  const data = { revision: 1, columns: ['STT', 'Tên nhân viên', 'Trạng thái', 'Phòng', 'Dịch vụ', 'Lịch hẹn', 'Vào ca'], records,
    capabilities: { appointment_edit: canEdit, operate: true, payment: true }, services: [{ id: 'body', name: 'Body 90', price: 100 }],
    state: { employees: payable ? [{ id: 'e1', name: 'An An', status: 'CHO THANH TOÁN', service: 'Body 90', room: '1.1', service_price: 100 }] : [] } }
  const writes = []
  let fail = conflict
  globalThis.__tourTestApi = {
    liveTour: async () => structuredClone(data),
    liveTourAction: async (body) => {
      writes.push(body)
      if (fail) { fail = false; data.revision++; throw Object.assign(new Error('Live Tour đã thay đổi ở thiết bị khác. Hãy làm mới rồi thao tác lại.'), { status: 409 }) }
      assert.equal(body.expected_revision, data.revision)
      assert.equal(body.action, 'update_appointment')
      records.find((record) => record._id === body.payload.employee_id)['Lịch hẹn'] = body.payload.appointment
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
    assert.equal(f.search().closest('label').nextElementSibling, f.quick())
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
    const picker = document.querySelector('.live-tour-employee-picker')
    assert.match(picker.textContent, /An An.*Body 90.*1\.1/)
    await act(async () => picker.querySelector('button').click())
    assert.match(document.querySelector('.live-tour-employee-picked').textContent, /Body 90/)
  } finally { await f.dispose() }
})

test.after(() => dom.window.close())
