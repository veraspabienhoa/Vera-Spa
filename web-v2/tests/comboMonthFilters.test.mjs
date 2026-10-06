import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'
import { violationMonthRange } from '../src/lib/businessMonthRange.js'
const bundle = await build({ stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Page from './src/pages/WorkSchedulePage';window.act=act;window.mount=()=>{window.root=createRoot(document.getElementById('root'));window.root.render(<Page user={{role:'letan',username:'Gia Anh',permissions:{work_schedule_letan:true}}}/>)};`, resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' }, define: { 'import.meta.env': JSON.stringify({ VITE_VERA_API_BASE_URL: 'https://api.test' }) }, plugins: [{ name: 'dependencies', setup(b) {
  b.onResolve({ filter: /\/lib\/(api|supabase)$/ }, args => ({ path: args.path.endsWith('supabase') ? 'auth' : 'api', namespace: 'mock' }))
  b.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: args.path === 'auth' ? 'export const getCurrentSession=async()=>({access_token:"test"});' : 'export const veraApi={exportComboSalesExcel:async(...args)=>window.exported=args};' }))
} }] })
test('combo month filters fetch the chosen period without reloading schedule and export that period', async t => {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window, calls = [], channels = []
  w.MessageChannel = class extends MessageChannel { constructor() { super(); channels.push(this) } }
  w.HTMLDialogElement.prototype.close = function () { this.open = false }; w.HTMLDialogElement.prototype.showModal = function () { this.open = true }
  w.Headers = Headers; w.IS_REACT_ACT_ENVIRONMENT = true
  const current = violationMonthRange(), previous = violationMonthRange(-1)
  w.fetch = async url => {
    calls.push(url); const path = new URL(url)
    let data = { rows: [] }
    if (path.pathname.endsWith('/combo-sales')) data.rows = [{ id: path.searchParams.get('start'), employee_username: 'Gia Anh', customer_name: path.searchParams.get('start') === previous.start ? 'Khách tháng trước' : 'Khách tháng này', sale_date: path.searchParams.get('start'), combo_ticket: 'Combo' }]
    else if (path.pathname === '/v2/work-schedule') data = { employees: [{ username: 'Gia Anh', role: 'letan', employment_status: 'Đang làm việc' }], rows: [], shift_definitions: { letan: { 'Ca 1': { start: '09:00', end: '17:00' } } } }
    return { ok: true, json: async () => data }
  }
  t.after(async () => { await w.act(() => w.root.unmount()); channels.forEach(c => { c.port1.close(); c.port2.close() }); w.close() })
  w.eval(bundle.outputFiles[0].text); await w.act(async () => w.mount())
  const doc = w.document, scheduleReads = () => calls.filter(url => new URL(url).pathname === '/v2/work-schedule').length
  const before = scheduleReads(), selectedMonth = doc.querySelector('.schedule-month-picker input').value
  const filterButton = text => [...doc.querySelectorAll('.combo-month-filters button')].find(b => b.textContent === text)
  assert.match(doc.querySelector('.combo-employee-card').textContent, /Khách tháng này/)
  await w.act(async () => filterButton('Tháng trước').click())
  assert.match(doc.querySelector('.combo-employee-card').textContent, /Khách tháng trước/)
  assert.equal(scheduleReads(), before); assert.equal(doc.querySelector('.schedule-month-picker input').value, selectedMonth)
  assert.ok(calls.some(url => url.includes('/combo-sales?start=' + previous.start + '&end=' + previous.end)))
  await w.act(async () => [...doc.querySelectorAll('.combo-excel-actions button')].find(b => b.textContent.trim() === 'Xuất excel').click())
  assert.deepEqual([...w.exported], [previous.start, previous.end, 'letan'])
  await w.act(async () => filterButton('Tháng này').click())
  assert.match(doc.querySelector('.combo-employee-card').textContent, /Khách tháng này/)
  assert.equal(filterButton('Tháng này').getAttribute('aria-pressed'), 'true')
  assert.ok(current.start)
})
