import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const built = await build({
  entryPoints: ['src/pages/EmployeePage.jsx'], bundle: true, write: false,
  platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  define: { 'import.meta.env': '{}' },
  plugins: [{ name: 'staff-transport', setup(builder) {
    builder.onResolve({ filter: /\/(api|supabase)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ loader: 'js', contents: path === 'api'
      ? 'export const apiRequest=async()=>({}); export const apiBinaryResponse=async()=>new Response(); export const isApiConfigured=true; export const veraApi=globalThis.__staffApi;'
      : 'export const getCurrentSession=async()=>null; export const refreshCurrentSession=getCurrentSession;'
    }))
  } }],
})

test('add employee modal preserves drafts, validates dates and handles pending, failed and successful saves', async () => {
  const dom = new JSDOM('<body><main></main></body>', { url: 'https://example.test', pretendToBeVisual: true })
  const requests = []
  let staffReads = 0, resolveCreate, rejectCreate
  const api = {
    staff: async () => {
      staffReads++
      return { employees: [], permissions: { employee_add: true }, role_options: ['nhanvien', 'letan'], status_options: [], cycle_options: [] }
    },
    createStaff: payload => {
      requests.push(payload)
      return new Promise((resolve, reject) => { resolveCreate = resolve; rejectCreate = reject })
    },
  }
  const globals = { window: dom.window, document: dom.window.document, __staffApi: api, IS_REACT_ACT_ENVIRONMENT: true }
  const saved = Object.fromEntries(Object.keys(globals).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(globals)) Object.defineProperty(globalThis, key, { value, configurable: true, writable: true })
  window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} })
  const { createRoot } = await import('react-dom/client')
  const mod = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
  const root = createRoot(document.querySelector('main'))
  const dialog = () => document.querySelector('[role="dialog"]')
  const inputFor = label => [...dialog().querySelectorAll('label')].find(node => node.textContent.startsWith(label)).querySelector('input, select')
  const fill = async (label, value) => {
    const input = inputFor(label)
    const prototype = input.tagName === 'SELECT' ? window.HTMLSelectElement.prototype : window.HTMLInputElement.prototype
    await act(async () => {
      Object.getOwnPropertyDescriptor(prototype, 'value').set.call(input, value)
      input.dispatchEvent(new window.Event(input.tagName === 'SELECT' ? 'change' : 'input', { bubbles: true }))
    })
  }
  try {
    await act(async () => root.render(React.createElement(mod.exports.default, { user: { role: 'quanly' } })))
    const opener = document.querySelector('[data-ui-key="u-dcce5ace3b12"]')
    assert.ok(opener)
    const open = async () => { opener.focus(); await act(async () => opener.click()) }
    await open()
    assert.equal(document.querySelector('main').contains(dialog()), false, 'modal must not expand the employee list')
    assert.equal(document.getElementById(dialog().getAttribute('aria-labelledby')).textContent, 'THÊM NHÂN VIÊN')
    assert.equal(document.body.style.overflow, 'hidden')
    assert.equal(dialog().querySelectorAll('[required]').length, 7)

    await fill('Tên nhân viên', 'Nhân viên thử')
    await fill('Mật khẩu ban đầu', 'test-pass-123')
    await act(async () => dialog().querySelector('[aria-label="Hiện mật khẩu"]').click())
    assert.equal(inputFor('Mật khẩu ban đầu').type, 'text')
    await act(async () => dialog().querySelector('[aria-label="Đóng thêm nhân viên"]').click())
    assert.equal(dialog(), null)
    assert.equal(document.body.style.overflow, '')
    assert.equal(document.activeElement, opener)
    await open()
    assert.equal(inputFor('Tên nhân viên').value, 'Nhân viên thử')
    assert.equal(inputFor('Mật khẩu ban đầu').type, 'password')
    await act(async () => dialog().dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true })))
    assert.equal(dialog(), null)
    await open()
    await fill('Họ và tên đầy đủ', 'Nguyễn Nhân viên thử')
    await fill('Phân quyền', 'letan')
    await fill('Giới tính', 'Nữ')
    await fill('Ngày bắt đầu làm', '27092026')
    await fill('Ngày sinh', '31022000')
    const form = dialog().querySelector('form')
    await act(async () => form.requestSubmit())
    assert.equal(requests.length, 0, 'invalid dates must not submit')
    await fill('Ngày sinh', '29022000')
    assert.equal(inputFor('Ngày sinh').value, '29-02-2000')
    await act(async () => {
      form.requestSubmit()
      form.dispatchEvent(new window.Event('submit', { bubbles: true, cancelable: true }))
    })
    assert.equal(requests.length, 1, 'rapid repeated submits send only one request')
    assert.equal(requests[0].birth_date, '29/02/2000')
    assert.equal(requests[0].employment_start_date, '27/09/2026')
    assert.equal(requests[0].role, 'letan')
    assert.equal(requests[0].username, 'Nhân viên thử')
    assert.ok(inputFor('Tên nhân viên').matches(':disabled'))
    assert.ok(dialog().querySelector('[type="submit"]').disabled)
    await act(async () => {
      dialog().querySelector('[data-ui-key="u-51288699be90"]').click()
      dialog().querySelector('[aria-label="Đóng thêm nhân viên"]').click()
      dialog().dispatchEvent(new window.KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    })
    assert.ok(dialog(), 'cannot close while saving')
    await act(async () => rejectCreate(new Error('Tên nhân viên đã tồn tại.')))
    assert.match(dialog().querySelector('[role="status"]').textContent, /Tên nhân viên đã tồn tại/)
    assert.equal(document.querySelector('main .staff-notice'), null, 'error is shown inside the active dialog')
    assert.equal(inputFor('Tên nhân viên').value, 'Nhân viên thử')
    assert.equal(inputFor('Tên nhân viên').matches(':disabled'), false)

    await fill('Tên nhân viên', 'Nhân viên mới')
    await act(async () => form.requestSubmit())
    await act(async () => resolveCreate({ message: 'Đã thêm nhân viên.' }))
    assert.equal(requests.length, 2)
    assert.equal(staffReads, 2, 'refresh the list once after a successful save')
    assert.equal(dialog(), null)
    assert.equal(document.body.style.overflow, '')
    assert.equal(document.activeElement, opener)
    assert.match(document.querySelector('main .staff-notice').textContent, /Đã thêm nhân viên/)
    await open()
    assert.equal(inputFor('Tên nhân viên').value, '')
    assert.equal(inputFor('Mật khẩu ban đầu').value, '')
    assert.equal(dialog().querySelector('[role="status"]'), null)
  } finally {
    await act(async () => root.unmount())
    dom.window.close()
    for (const [key, value] of Object.entries(saved)) {
      if (value) Object.defineProperty(globalThis, key, value)
      else delete globalThis[key]
    }
  }
})
