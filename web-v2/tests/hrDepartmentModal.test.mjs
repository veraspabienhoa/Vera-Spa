import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const built = await build({ stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Page from './src/pages/HumanResourcesPage';import {startSystemFeedback} from './src/lib/systemFeedback';const root=createRoot(document.getElementById('root'));const stop=startSystemFeedback();window.act=act;window.mount=()=>act(async()=>root.render(<Page user={{role:'admin'}}/>));window.unmount=()=>act(async()=>{root.unmount();stop()});`, resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' }, plugins: [{ name: 'api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi=window.api;' }))
} }] })

test('HR creates an inactive code, shows success/errors as modals and never deletes before confirmation', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true }), w = dom.window
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.IS_REACT_ACT_ENVIRONMENT = true
  let state = { departments: { kho: { name: 'Kho cũ', active: false, salary_mode: 'monthly' } }, revision: 7, employees: [], commission: null }, deletes = 0, sent
  w.api = {
    hr: async () => structuredClone(state),
    saveHrDepartment: async body => { sent = body; if (state.departments[body.code]?.active && body.creating) throw Error('Mã bộ phận đã tồn tại. Hãy chọn Sửa hoặc dùng mã mới.'); state = { ...state, revision: state.revision + 1, departments: { ...state.departments, [body.code]: { name: body.name, salary_mode: body.salary_mode, active: true } } } },
    deleteHrDepartment: async (code, revision) => { assert.equal(revision, state.revision); deletes++; state.departments[code].active = false; state.revision++ },
  }
  w.eval(built.outputFiles[0].text)
  const click = selector => w.act(async () => w.document.querySelector(selector).click())
  const fill = (node, value) => w.act(async () => { Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, 'value').set.call(node, value); node.dispatchEvent(new w.Event('input', { bubbles: true })) })
  const submit = () => w.act(async () => w.document.querySelector('.hr-department-form').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true })))
  try {
    await w.mount()
    const inputs = () => w.document.querySelectorAll('.hr-department-form input')
    await fill(inputs()[0], 'kho'); await fill(inputs()[1], 'Kho mới'); await submit()
    assert.equal(sent.creating, true); assert.equal(sent.revision, 7)
    assert.match(w.document.querySelector('.system-dialog-success').textContent, /Đã lưu bộ phận/)
    assert.ok(w.document.querySelector('.success-box').hasAttribute('data-feedback-presented'))
    await click('.system-dialog .primary-button')
    await fill(inputs()[0], 'kho'); await fill(inputs()[1], 'Kho trùng'); await submit()
    assert.match(w.document.querySelector('.system-dialog-error').textContent, /Mã bộ phận đã tồn tại/)
    assert.equal(inputs()[1].value, 'Kho trùng', 'failed save preserves the form')
    await click('.system-dialog .primary-button')
    await submit()
    assert.match(w.document.querySelector('.system-dialog-error')?.textContent || '', /Mã bộ phận đã tồn tại/, 'repeating a failed save must show the error again')
    await click('.system-dialog .primary-button')
    await click('.hr-actions .danger-button'); assert.equal(deletes, 0)
    await click('.system-dialog .secondary-button'); assert.equal(deletes, 0)
    await click('.hr-actions .danger-button'); await click('.system-dialog .primary-button')
    assert.equal(deletes, 1); assert.match(w.document.querySelector('.system-dialog-success').textContent, /Đã xóa bộ phận/)
  } finally { await w.unmount(); w.close() }
})
