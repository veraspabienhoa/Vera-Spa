import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({ stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Page from './src/pages/ResidencePage';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=()=>act(async()=>root.render(<Page user={{role:'admin'}}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' }, plugins: [{ name: 'api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
  b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: 'export const veraApi=window.api;' }))
} }] })
test('residence persists membership, exports filters and confirms removal', async () => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true }), w = dom.window
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.IS_REACT_ACT_ENVIRONMENT = true
  let included = false, writes = 0, exported
  const documents = []
  w.URL.createObjectURL = () => "blob:residence-test"
  w.URL.revokeObjectURL = () => {}
  const person = {username:'Ngọc Như',full_name:'Synthetic',department:'Lễ tân',department_code:'letan'}
  w.api = {
    residence: async () => ({columns:[{key:'username',label:'Tên nhân viên'}],records:included?[person]:[],employees:[{...person,included}],departments:[{code:'letan',name:'Lễ tân'}]}),
    saveResidence: async body => { included = body.included; writes++; return {message:'Đã lưu'} },
    exportResidence: async args => { exported = args },
    readResidenceExport: async (format, filters) => { documents.push({format, filters});return {blob:new w.Blob([format]),filename:`TamTru.${format}`} },
  }
  w.eval(built.outputFiles[0].text)
  const click = selector => w.act(async () => w.document.querySelector(selector).click())
  const button = text => [...w.document.querySelectorAll('button')].find(b => b.textContent===text)
  try {
    await w.mount()
    await w.act(async () => { w.document.querySelector('.residence-picker input').focus() })
    await click('[role=option][id]')
    await w.act(async () => button('Thêm').click())
    assert.equal(writes,1)
    assert.match(w.document.querySelector('tbody').textContent,/Ngọc Như/)
    await click('.system-dialog .primary-button')
    await w.act(async () => { const s=w.document.querySelector('select');s.value='letan';s.dispatchEvent(new w.Event('change',{bubbles:true})) })
    await w.act(async () => button('Xuất Excel').click())
    assert.equal(exported.department,'letan')
    await w.act(async () => button('Xem / tải / chia sẻ PNG và PDF').click())
    assert.deepEqual(documents.map(x=>x.format).sort(), ['pdf','png'])
    assert.ok(documents.every(x=>x.filters.department==='letan'))
    assert.equal(w.document.querySelectorAll('a[download]').length,2)
    assert.match(w.document.querySelector('[role=dialog]').textContent,/Xem PDF/)
    await w.act(async () => button('Đóng').click())
    await w.act(async () => button('Bỏ khỏi bảng').click())
    assert.equal(writes,1)
    await click('.system-dialog .secondary-button')
    assert.equal(writes,1)
    await w.act(async () => button('Bỏ khỏi bảng').click())
    await click('.system-dialog .primary-button')
    assert.equal(writes,2)
    assert.equal(w.document.querySelectorAll('tbody tr').length,0)
  } finally { await w.unmount();w.close() }
})
