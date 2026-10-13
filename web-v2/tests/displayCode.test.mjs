import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { displayCode } from '../src/lib/displayCode.js'
import { checkinLookupOptions } from '../src/lib/checkinHistory.js'

const id = '6897bf10-398e-49e7-8679-950006a7e369'
test('long display codes are abbreviated; short and zero-prefixed codes remain intact', () => {
  assert.equal(displayCode(id), '6897bf10…e369')
  for (const code of ['000123', 'NV-0123', 'KH-42', 0]) assert.equal(displayCode(code), String(code))
  for (const code of [null, undefined, '']) assert.equal(displayCode(code), '—')
})
test('employee lookup retains complete IDs for queries and full-code searching', () => {
  const { employees } = checkinLookupOptions([{ employee_code: id }])
  assert.equal(employees[0].value, id)
  assert.equal(employees[0].label, displayCode(id))
  assert.equal(employees[0].detail, displayCode(id))
  assert.equal(employees[0].searchText, id)
})
test('compact codes expand on touch/click without submitting a form or opening the parent card', async () => {
  const built = await build({ stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Code from './src/components/CompactCode';window.act=act;window.root=createRoot(document.getElementById('root'));window.mount=()=>window.root.render(<form onSubmit={e=>{e.preventDefault();window.submitted=true}}><div onClick={()=>window.opened=true}><Code value="${id}" label="Mã khách hàng"/></div></form>);`, resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' } })
  const dom = new JSDOM('<div id="root"></div>', { runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.IS_REACT_ACT_ENVIRONMENT = true
  w.eval(built.outputFiles[0].text)
  try {
    await w.act(async () => w.mount())
    const button = w.document.querySelector('button')
    assert.equal(button.textContent, displayCode(id))
    assert.equal(button.title, id)
    await w.act(async () => button.click())
    assert.equal(button.textContent, id)
    assert.equal(button.getAttribute('aria-expanded'), 'true')
    assert.equal(w.submitted, undefined)
    assert.equal(w.opened, undefined)
    await w.act(async () => button.click())
    assert.equal(button.textContent, displayCode(id))
  } finally { await w.act(async () => w.root.unmount()); w.close() }
})
