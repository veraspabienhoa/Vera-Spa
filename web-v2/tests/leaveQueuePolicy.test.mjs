import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Panel from './src/pages/LeaveQueuePolicyRules';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=canEdit=>act(async()=>root.render(<Panel policy={window.policy} canEdit={canEdit}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic',
  plugins: [{ name: 'api', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: `export const veraApi={saveLeaveQueuePolicy:async body=>{window.sent.push(body);if(window.fail)throw Error('Nội quy đã thay đổi');return {...body,revision:body.expected_revision+1,available_reasons:window.policy.available_reasons,message:'Đã lưu'}}};` }))
  } }],
})
async function mount(canEdit) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.IS_REACT_ACT_ENVIRONMENT = true
  w.sent = []; w.policy = { enabled: true, reasons: ['Về sớm CÓ phép', 'Nghỉ KHÔNG phép'], available_reasons: ['Về sớm CÓ phép', 'Nghỉ KHÔNG phép'], revision: 3 }
  w.eval(built.outputFiles[0].text); await w.mount(canEdit)
  return dom
}
test('admin can disable all, select one, enable all; failure preserves saved state', async () => {
  const dom = await mount(true), w = dom.window
  const button = text => [...w.document.querySelectorAll('button')].find(b => b.textContent === text)
  try {
    await w.act(async () => button('Tắt tất cả').click())
    assert.equal(w.sent[0].enabled, false); assert.equal(w.sent[0].expected_revision, 3)
    assert.equal(w.document.querySelectorAll('input:checked').length, 0)
    await w.act(async () => w.document.querySelector('input').click())
    assert.equal(w.sent[1].reasons.length, 1); assert.equal(w.sent[1].expected_revision, 4)
    assert.equal(w.document.querySelectorAll('input:checked').length, 1)
    await w.act(async () => button('Kích hoạt tất cả').click())
    assert.equal(w.document.querySelectorAll('input:checked').length, 2)
    w.fail = true
    await w.act(async () => button('Tắt tất cả').click())
    assert.ok(w.document.querySelector('[role="alert"]'))
    assert.equal(w.document.querySelectorAll('input:checked').length, 2)
  } finally { await w.unmount(); w.close() }
})
test('non-admin sees policy without editable controls', async () => {
  const dom = await mount(false), w = dom.window
  try {
    assert.equal(w.document.querySelectorAll('button').length, 0)
    assert.equal(w.document.querySelector('fieldset').disabled, true)
    assert.equal(w.sent.length, 0)
  } finally { await w.unmount(); w.close() }
})
