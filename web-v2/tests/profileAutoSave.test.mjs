import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/ProfilePage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'lucide-react'],
  plugins: [{ name: 'fixture', setup(b) {
    b.onResolve({ filter: /\/lib\/(api|profileReferenceRefresh|pushNotifications)$|EmployeeIdentityPanel$/ }, (args) => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({ contents: {
      api: 'export const veraApi = globalThis.__profileApi;',
      profileReferenceRefresh: 'export const refreshProfileReferenceData = async()=>({});',
      EmployeeIdentityPanel: 'export default function Panel(){return null}',
      pushNotifications: 'export const disablePushNotifications = async()=>({}); export const enablePushNotifications = async()=>({}); export const readPushState = async()=>({}); export const syncExistingPushSubscription = async()=>({});',
    }[path], loader: 'js' }))
  } }],
})

test('profile autosaves, retains later edits and never sends an incomplete or mismatched password', async () => {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
  const descriptors = Object.fromEntries(['window', 'document', 'navigator', 'CustomEvent', 'IS_REACT_ACT_ENVIRONMENT', '__profileApi'].map((key) => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  Object.defineProperties(globalThis, {
    window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
    navigator: { value: dom.window.navigator, configurable: true }, CustomEvent: { value: dom.window.CustomEvent, configurable: true },
    IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
  })
  const calls = []
  let resolveSave
  const api = {
    profile: async () => ({ profile: { username: 'Tester', full_name: 'Test' } }),
    profileReferenceData: async () => ({ provinces: [], banks: [] }),
    updateProfile: (payload) => { calls.push(payload); return new Promise((resolve) => { resolveSave = resolve }) },
  }
  globalThis.__profileApi = api
  const { createRoot } = await import('react-dom/client')
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  const root = createRoot(document.querySelector('#root'))
  let timer
  window.setTimeout = (callback, delay) => { if (delay === 900) timer = callback; return 1 }
  window.clearTimeout = () => { timer = undefined }
  const tick = async () => { const fn = timer; timer = undefined; await act(async () => fn?.()) }
  const field = (label) => [...document.querySelectorAll('label')].find((item) => item.textContent.startsWith(label)).querySelector('input')
  const edit = async (input, value) => act(() => {
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set.call(input, value)
    input.dispatchEvent(new window.Event('input', { bubbles: true }))
  })
  try {
    await act(async () => root.render(React.createElement(module.exports.default, { user: { role: 'nhanvien', employee_username: 'Tester' }, onPasswordChanged() {} })))
    await tick()
    assert.equal(calls.length, 0, 'initial load must not save')
    await edit(field('Điện thoại'), '0901')
    await tick()
    assert.equal(calls.length, 1)
    assert.equal(calls[0].phone, '0901')
    assert.equal('current_password' in calls[0], false)
    await edit(field('Điện thoại'), '0902')
    await tick()
    assert.equal(calls.length, 1, 'serialize requests')
    await act(async () => resolveSave({ message: 'Đã lưu' }))
    assert.equal(field('Điện thoại').value, '0902', 'do not overwrite a later edit')
    await tick()
    assert.equal(calls.length, 2)
    assert.equal(calls[1].phone, '0902')
    await act(async () => resolveSave({ message: 'Đã lưu' }))
    await edit(field('Mật khẩu hiện tại'), 'OldSecret9!')
    await edit(field('Mật khẩu mới'), 'NextSecret9!')
    await tick()
    assert.equal(calls.length, 2)
    await edit(field('Xác nhận mật khẩu mới'), 'Different9!')
    await tick()
    assert.equal(calls.length, 2)
    await edit(field('Xác nhận mật khẩu mới'), 'NextSecret9!')
    await tick()
    assert.equal(calls.length, 3)
    assert.equal(calls[2].new_password, 'NextSecret9!')
    await act(async () => resolveSave({ message: 'Đã đổi', password_changed: true }))
    await tick()
    assert.equal(calls.length, 3, 'do not repeat after password changes')
    assert.equal(field('Mật khẩu mới').value, '')
  } finally {
    await act(() => root.unmount())
    dom.window.close()
    for (const [key, descriptor] of Object.entries(descriptors)) {
      if (descriptor) Object.defineProperty(globalThis, key, descriptor)
      else delete globalThis[key]
    }
  }
})
