import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'

const built = await build({ stdin: { contents: `import React,{act} from 'react';import{createRoot}from'react-dom/client';import Page from './src/pages/CheckinHistoryPage';import Preview from './src/components/FacegateAttendancePreview';window.act=act;window.mount=(role,history)=>{window.root=createRoot(document.getElementById('root'));window.root.render(history?<Page user={{role,permissions:{device_facegate_mapping_manage:true}}}/>:<Preview/>)};`, resolveDir: process.cwd(), loader: 'jsx' }, bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' }, plugins: [{ name: 'api', setup(b) {
  b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'mock' }))
  b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export const veraApi=window.api;', loader: 'js' }))
} }] })
async function page(ctx, role, api = {}, history = false) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://test.invalid', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window, channels = []
  w.MessageChannel = class extends MessageChannel { constructor() { super(); channels.push(this) } }
  w.IS_REACT_ACT_ENVIRONMENT = true; w.api = api; w.eval(built.outputFiles[0].text)
  await w.act(async () => w.mount(role, history))
  ctx.after(async () => { await w.act(async () => w.root.unmount()); channels.forEach(c => { c.port1.close(); c.port2.close() }); w.close() })
  return { w, panel: () => w.document.querySelector('.facegate-attendance-preview'),
    async input(node, value) { await w.act(async () => { Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype, 'value').set.call(node, value); node.dispatchEvent(new w.Event('input', { bubbles: true })) }) },
    async submit() { await w.act(async () => w.document.querySelector('.facegate-attendance-preview form').dispatchEvent(new w.Event('submit', { bubbles: true, cancelable: true }))) } }
}
const report = { start: '2026-09-26', end: '2026-09-26', facegate_event_count: 3, differences: [], evidence_differences: [], issue_count: 0, blockers: ['production_cutover_review_required'], unmapped_employees: [], incomplete_days: [], mapping_candidates: [], issues: [], last_sync_at: '2026-09-27T01:00:00+07:00', records: [{ date: '26/09/2026', employee_name: 'Ánh Thử', shift: 'Ca đêm', overnight_shift: true, check_in_at: '2026-09-27T00:30:00+07:00', punch_datetimes: ['2026-09-27T00:30:00'], break_out: '', break_in: '' }] }

test('admin preview is lazy, applies edited ISO dates and retains Vietnamese names and overnight dates', async ctx => {
  const calls = []
  const p = await page(ctx, 'admin', { previewFacegateAttendance: async (...args) => { calls.push(args); return report } })
  assert.equal(calls.length, 0)
  const inputs = p.panel().querySelectorAll('input[type=text]')
  await p.input(inputs[0], '26092026'); await p.input(inputs[1], '26092026'); await p.submit()
  assert.deepEqual(calls, [['2026-09-26', '2026-09-26']])
  assert.match(p.panel().textContent, /Ánh Thử/)
  assert.match(p.panel().textContent, /27-09-2026 00:30:00/)
  assert.match(p.panel().textContent, /Nguồn chính hiện tại được hiển thị tại mục Thiết bị/)
  await p.input(inputs[0], '25092026')
  assert.equal(p.panel().querySelector('table'), null)
})

for (const role of ['admin', 'letan', 'quanly', 'nhanvien']) {
  test(`check-in history omits both maintenance panels for ${role}`, async ctx => {
    const p = await page(ctx, role, {}, true)
    assert.equal(p.panel(), null)
    assert.doesNotMatch(p.w.document.body.textContent, /Ánh xạ hồ sơ FaceGate với nhân viên|Đối chiếu FaceGate → Chấm công VERA/)
    assert.match(p.w.document.body.textContent, /LỊCH SỬ CHECK IN/)
    assert.match(p.w.document.body.textContent, /Xem lịch sử/)
    assert.match(p.w.document.body.textContent, /Xuất excel/)
  })
}

test('range is bounded and network failure leaves retry available', async ctx => {
  let calls = 0
  const p = await page(ctx, 'admin', { previewFacegateAttendance: async () => { calls++; throw Error('Chưa có kết nối') } })
  const inputs = p.panel().querySelectorAll('input[type=text]')
  await p.input(inputs[0], '01092026'); await p.input(inputs[1], '26092026'); await p.submit()
  assert.equal(calls, 0); assert.match(p.panel().textContent, /1 đến 7 ngày/)
  await p.input(inputs[0], '26092026'); await p.submit()
  assert.equal(calls, 1); assert.match(p.panel().textContent, /Chưa có kết nối/)
  assert.equal(p.panel().querySelector('button[type=submit]').disabled, false)
})

test('FaceGate basic payroll uses selected dates and shows pending money without zero salary', async ctx => {
  const calls=[]
  const p=await page(ctx,'admin',{ previewFacegatePayroll:async (...args)=>{
    calls.push(args)
    return {start:'2026-09-29',end:'2026-09-29',pending_count:1,estimated_basic_pay_total:0,blockers:[],rows:[{
      employee_username:'Yến Linh',employee_name:'Yến Linh',department_label:'Lễ tân',hours:null,
      basic_salary_estimate:null,pending_reasons:['Chưa đủ giờ vào/ra']
    }]}
  }})
  const inputs=p.panel().querySelectorAll('input[type=text]')
  await p.input(inputs[0],'29092026'); await p.input(inputs[1],'29092026')
  const button=[...p.panel().querySelectorAll('button')].find(b=>b.textContent==='Tính lương cơ bản từ FaceGate')
  await p.w.act(async()=>button.click())
  assert.deepEqual(calls,[['2026-09-29','2026-09-29']])
  const section=p.panel().querySelector('[aria-label="Lương cơ bản FaceGate"]')
  assert.match(section.textContent,/Chưa lưu bảng lương chính thức/)
  assert.match(section.querySelector('tbody tr').textContent,/Chờ bổ sung/)
  assert.doesNotMatch(section.querySelector('tbody tr').textContent,/0 ₫/)
  await p.input(inputs[0],'28092026')
  assert.equal(p.panel().querySelector('[aria-label="Lương cơ bản FaceGate"]'),null)
})
