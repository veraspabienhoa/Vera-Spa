import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Table from './src/components/PayrollObligationTable';import {combineObligationGroups} from './src/lib/payrollObligationGroups';const root=createRoot(document.getElementById('root'));window.act=act;window.combine=combineObligationGroups;window.mount=groups=>act(async()=>root.render(<Table groups={groups}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic',
})
const groups = [
  { type: 'Âm thực nhận', summary: [{ employee_name: 'An Nhiên', total: 300000 }, { employee_name: 'B', total: 100000 }], details: [
    { employee_name: 'An Nhiên', amount: 300000, period_start: '2026-09-01', period_end: '2026-09-15', due_from: '16/09/2026', content: 'Nợ kỳ 1', status: 'Chưa hoàn thành', type: 'Âm thực nhận' },
    { employee_name: 'B', amount: 100000, type: 'Âm thực nhận' },
  ] },
  { type: 'Tạm hoãn vi phạm', summary: [{ employee_name: ' AN NHIÊN ', total: 500000 }], details: [
    { employee_name: ' AN NHIÊN ', amount: 200000, period_start: '2026-09-01', period_end: '2026-09-15', due_from: '2026-10-01', content: 'Khoản 1', status: 'Chưa hoàn thành' },
    { employee_name: ' AN NHIÊN ', amount: 300000, period_start: '2026-09-01', period_end: '2026-09-15', due_from: '2026-10-01', content: 'Khoản 2', status: 'Chưa hoàn thành' },
  ] },
]
function setup() {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  dom.window.IS_REACT_ACT_ENVIRONMENT = true
  dom.window.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  dom.window.eval(built.outputFiles[0].text)
  return dom
}
test('combines both types once per employee while preserving separate amounts and every claim', async () => {
  const dom = setup(), w = dom.window, original = JSON.stringify(groups)
  try {
    const result = w.combine(groups)
    assert.equal(result.length, 2)
    assert.equal(result[0].employee_name, 'An Nhiên')
    assert.equal(result[0].negative, 300000)
    assert.equal(result[0].deferred, 500000)
    assert.equal(result[0].total, 800000)
    assert.equal(result[0].details.length, 3)
    assert.equal(result[0].details[2].type, 'Tạm hoãn vi phạm')
    assert.equal(result[1].deferred, 0)
    assert.equal(JSON.stringify(groups), original)
  } finally { await w.unmount(); w.close() }
})
test('opens employee details with debt type, dates and status, and handles empty refresh', async () => {
  const dom = setup(), w = dom.window
  try {
    await w.mount(groups)
    assert.equal(w.document.querySelectorAll('table').length, 1)
    const button = w.document.querySelector('button')
    await w.act(async () => button.click())
    assert.equal(button.getAttribute('aria-expanded'), 'true')
    const detail = w.document.querySelector('table[aria-label="Chi tiết nợ An Nhiên"]')
    assert.equal(detail.querySelectorAll(':scope > tbody > tr').length, 3)
    assert.ok(detail.textContent.includes('16-09-2026'))
    assert.ok(detail.textContent.includes('01-10-2026'))
    assert.ok(detail.textContent.includes('Âm thực nhận'))
    assert.ok(detail.textContent.includes('Tạm hoãn vi phạm'))
    assert.ok(detail.textContent.includes('Chưa hoàn thành'))
    await w.act(async () => button.click())
    assert.equal(w.document.querySelectorAll('table').length, 1)
    await w.mount([])
    assert.ok(w.document.body.textContent.includes('Không có khoản đang mở.'))
  } finally { await w.unmount(); w.close() }
})
