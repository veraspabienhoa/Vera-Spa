import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'http://localhost', pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, localStorage: { value: dom.window.localStorage, configurable: true },
  IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
async function component(path) {
  const result = await build({ entryPoints: [fileURLToPath(new URL(`../src/${path}.jsx`, import.meta.url))], bundle: true,
    write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'],
    loader: { '.css': 'empty' }, define: { 'import.meta.env': '{}' }, plugins: [{ name: 'offline-data', setup(b) {
      b.onResolve({ filter: /(^|\/)(api|data)$/ }, args => ({ path: args.path.endsWith('/api') ? 'api' : 'data', namespace: 'mock' }))
      b.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: args.path === 'api'
        ? 'export const isApiConfigured=false; export const veraApi={};'
        : 'export const loadEmployees=async()=>{globalThis.leaveReads++;return []}; export const loadLeaveRecords=loadEmployees; export const loadLeaveReasons=loadEmployees; export const loadLeaveDailyStats=loadEmployees;', loader: 'js' }))
    } }] })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', result.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const LeavePage = await component('pages/LeaveRegistrationPage')
const PaidPanel = await component('components/LiveTourInvoicesPanel')
test('three leave tabs show one panel, retain unsaved input and do not reload data', async () => {
  globalThis.leaveReads = 0
  const root = createRoot(document.querySelector('#root'))
  try {
    await act(async () => root.render(React.createElement(LeavePage, { user: { role: 'admin', permissions: {} } })))
    const tabs = [...document.querySelectorAll('[role="tab"]')]
    assert.deepEqual(tabs.map(node => node.textContent), ['Đăng ký', 'Thống kê', 'Danh sách'])
    const visible = () => [...document.querySelectorAll('[role="tabpanel"]')].filter(node => !node.hidden).map(node => node.id)
    assert.deepEqual(visible(), ['leave-panel-registration'])
    const textarea = document.querySelector('.registration-panel textarea')
    await act(() => {
      Object.getOwnPropertyDescriptor(dom.window.HTMLTextAreaElement.prototype, 'value').set.call(textarea, 'Ghi chú chưa lưu')
      textarea.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
    })
    const reads = globalThis.leaveReads
    await act(() => tabs[1].click())
    assert.deepEqual(visible(), ['leave-panel-statistics'])
    await act(() => tabs[2].click())
    assert.deepEqual(visible(), ['leave-panel-list'])
    await act(() => tabs[0].click())
    assert.equal(textarea.value, 'Ghi chú chưa lưu')
    assert.equal(globalThis.leaveReads, reads)
  } finally { await act(() => root.unmount()) }
})
test('paid invoice button exports paid ledger and disables when grant is missing or action is busy', async () => {
  const root = createRoot(document.querySelector('#root'))
  const calls = []
  const props = { visibleInvoices: [], canExportKind: () => true, exportData: kind => calls.push(kind) }
  try {
    await act(() => root.render(React.createElement(PaidPanel, props)))
    const button = () => [...document.querySelectorAll('button')].find(node => node.textContent.includes('Xuất excel'))
    await act(() => button().click())
    assert.deepEqual(calls, ['paid'])
    await act(() => root.render(React.createElement(PaidPanel, { ...props, canExportKind: () => false })))
    assert.equal(button().disabled, true)
    await act(() => root.render(React.createElement(PaidPanel, { ...props, actionBusy: 'export-paid' })))
    assert.equal(button().disabled, true)
  } finally { await act(() => root.unmount()) }
})
