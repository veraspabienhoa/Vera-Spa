import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React,{act} from 'react'
import {JSDOM as BaseJSDOM} from 'jsdom'
import { answerDialogs } from './dialogAnswers.mjs'
class JSDOM extends BaseJSDOM { constructor(...args) { super(...args); this.stopDialogAnswers = answerDialogs(this.window) } }
const bootstrap=new JSDOM('<body/>');globalThis.window=bootstrap.window;globalThis.document=bootstrap.window.document;after(()=>bootstrap.window.close())
const built=await build({stdin:{contents:`export {fitPayrollTable} from './src/lib/useFitPayrollTables';export {default as Panel} from './src/pages/DepartmentPayrollPanel';export {default as Settings} from './src/pages/DepartmentPayrollSettingsPage';export {default as Tabs} from './src/components/PayrollTabs';export {recoverablePage} from './src/lib/recoverablePage'`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic",refresh_token:"refresh"});export const refreshCurrentSession=async()=>({access_token:"renewed"});export const isSupabaseConfigured=false;export const supabase=null'}))}}]})
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
const {Panel,Settings,Tabs,recoverablePage,fitPayrollTable}=mod.exports,h=React.createElement
const config={calculation_mode:'hourly',rate_ca1:27000,rate_ca2_before_22:30000,rate_ca2_after_22:33000}
const rows=[['a','Nhân Viên A','letan','Lễ tân',500000],['b','Quản Lý B','quanly','Quản lý',300000],['c','Nhân Viên C','letan','Lễ tân',0]].map(([id,name,dep,label,combo],i)=>({employee_username:id,employee_name:name,email:`${id}@example.test`,department:dep,department_label:label,tt:i+1,work_days:1,hours_ca1:8,combo_sales:combo,salary:216000,total_salary:216000+combo,net_salary:216000+combo,calculation_config:config,calculation_source:'schedule'}))
async function fixture(t, expireSave=false, calculatedRows=rows){
 const dom=new JSDOM('<body><div id="root"/></body>',{url:'https://example.test',pretendToBeVisual:true}),requests=[];let draftRows=[],draftRevision=0,historyRevision=0,draftHistoryId=''
 const data={hc_payroll_contract:1,employee_config_revision:1,departments:{letan:{department_label:'Lễ tân',config},quanly:{department_label:'Quản lý',config},tapvu:{department_label:'Tạp vụ',config:{calculation_mode:'monthly'}}},salary_config_tables:{operations:[{employee_username:'a',employee_name:'Nhân Viên A',department:'letan',department_label:'Lễ tân',...config}],tapvu:[]},salary_employee_catalog:[{employee_username:'a',employee_name:'Nhân Viên A',department:'letan',department_label:'Lễ tân',salary_source:'schedule'}]}
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,fetch:async(url,options={})=>{
  const path=new URL(url).pathname;requests.push({path,url,options})
  if(expireSave && path.endsWith('/settings/employees') && requests.filter(r=>r.path===path).length===1) return new Response(JSON.stringify({detail:"expired"}),{status:401})
  if(path.endsWith('/draft') && options.method==='DELETE') draftRows=[]
  if(path.endsWith('/draft') && options.method==='PUT') { draftRows=JSON.parse(options.body).rows; draftHistoryId=JSON.parse(options.body).history_id||''; draftRevision++ }
  if(path.endsWith('/complete')) { draftRevision++; historyRevision++ }
  const body=path.endsWith('/settings/employees')?{salary_config_tables:{operations:(JSON.parse(options.body).rows||data.salary_config_tables.operations).filter(row=>row.department!=='tapvu'),tapvu:(JSON.parse(options.body).rows||data.salary_config_tables.tapvu).filter(row=>row.department==='tapvu')},employee_config_revision:2,salary_employee_catalog:data.salary_employee_catalog.map(row=>({...row,salary_source:JSON.parse(options.body).salary_sources?.find(item=>item.employee_username===row.employee_username)?.salary_source||row.salary_source})),message:'Đã lưu cấu hình'}:path.endsWith('/settings')?data:path.endsWith('/history')?{items:[],history_revision:historyRevision}:path.endsWith('/calculate')?{rows:calculatedRows,draft_revision:draftRevision,history_revision:historyRevision,start:'2026-09-01',end:'2026-09-26',source_label:'Theo cấu hình từng nhân viên'}:path.endsWith('/draft')?{rows:draftRows,history_id:draftHistoryId,draft_revision:draftRevision,history_revision:historyRevision,message:'Đã lưu'}:path.endsWith('/complete')?{rows:JSON.parse(options.body).rows,draft_revision:draftRevision,history_revision:historyRevision,history_id:'history-1',message:'Đã hoàn thành'}:{}
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
 }}
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true};dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}})
 return{requests,data,unmount:()=>act(()=>root.unmount()),manualDialogs:()=>dom.stopDialogAnswers(),render:element=>act(async()=>root.render(element)),click:async label=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===label);assert.ok(b,label);await act(async()=>b.click())},change:async(node,value)=>act(async()=>{Object.getOwnPropertyDescriptor(node.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event(node.tagName==='SELECT'?'change':'input',{bubbles:true}))})}
}
test('filters combine without requests or lost edits; save keeps the full payroll',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình')
 const count=()=>document.querySelectorAll('.department-payroll-table tbody tr').length
 assert.equal(count(),3)
 const search=document.querySelector('.department-payroll-table-search input'),department=document.querySelector('.department-payroll-department-filter select'),calls=f.requests.length
 await f.change(search,'nhan vien');assert.equal(count(),2)
 await f.change(department,'quanly');assert.equal(count(),0)
 await f.change(search,'');assert.equal(count(),1)
 assert.match(document.querySelector('.department-payroll-summary').textContent,/516\.000đ/);assert.equal(f.requests.length,calls)
 await f.change(document.querySelector('[aria-label="Trách nhiệm Quản Lý B"]'),'123.000')
 await f.change(department,'letan');await f.change(department,'quanly')
 assert.equal(document.querySelector('[aria-label="Trách nhiệm Quản Lý B"]').value,'123.000')
 window.HTMLAnchorElement.prototype.click=()=>{}
 await f.click('Xuất excel')
 assert.deepEqual(JSON.parse(f.requests.find(r=>r.path.endsWith('/export.xlsx')).options.body).rows.map(r=>r.employee_username),['b'])
 await f.click('Lưu bảng nháp');const saved=JSON.parse(f.requests.find(r=>r.path.endsWith('/draft')).options.body)
 assert.equal(saved.rows.length,3);assert.equal(saved.rows.find(r=>r.employee_username==='b').responsibility,123000)
})
test('Admin configuration opens with actual fields and preserves the other tab draft',async t=>{
 const f=await fixture(t);await f.render(h(Tabs,{user:{role:'admin'},ktv:h('input',{id:'ktv-draft',defaultValue:'draft'}),administrative:h(Panel,{user:{role:'admin'}}),configuration:h(Settings,{user:{role:'admin'}})}))
 const input=document.querySelector('#ktv-draft');input.value='unsaved'
 await f.click('Cấu hình lương');assert.ok(document.querySelector('.department-payroll-config-page'));assert.equal(document.querySelectorAll('.department-config-table tbody tr').length,1)
 assert.ok([...document.querySelectorAll('button')].some(b=>b.textContent.trim()==='Lưu toàn bộ cấu hình'))
 await f.click('Lương KTV');assert.equal(document.querySelector('#ktv-draft'),input);assert.equal(input.value,'unsaved')
 await f.click('Cấu hình lương');assert.equal(document.querySelectorAll('.department-config-table tbody tr').length,1)
})
test('configuration import failure preserves tabs and retry resets the correct module',async t=>{
 const f=await fixture(t);let attempts=0
 const Page=recoverablePage(async()=>{if(++attempts===1)throw Error('module unavailable');return{default:()=>h('p',{id:'config-ready'},'Ready')}})
 const original=console.error;console.error=()=>{};t.after(()=>{console.error=original});window.addEventListener('error',e=>e.preventDefault())
 await f.render(h(Tabs,{user:{role:'admin'},ktv:h('input',{id:'draft'}),configuration:h(Page)}));await f.click('Cấu hình lương')
 assert.ok(document.querySelector('[role="tablist"]'));assert.equal(new URL(document.querySelector('.page-recovery a').href).searchParams.get('page'),'payroll-config')
 await f.click('Thử mở lại');assert.equal(attempts,2);assert.ok(document.querySelector('#config-ready'))
})
test('non-Admin roles do not get the configuration tab',async t=>{
 const f=await fixture(t);await f.render(h(Tabs,{user:{role:'letan',permissions:{payroll_calculate:true}},administrative:h('p',null,'Payroll'),configuration:h('p',null,'Secret')}))
 assert.equal(document.querySelectorAll('[role="tab"]').length,1);assert.doesNotMatch(document.body.textContent,/Cấu hình lương|Secret/)
})

test('configuration saves numeric wages and places the separate source table last',async t=>{
 const f=await fixture(t);await f.render(h(Settings,{user:{role:'admin'}}))
 await f.change(document.querySelector('.department-config-table input'),'45.000')
 await f.click('Lưu cấu hình')
 const saved=JSON.parse(f.requests.find(r=>r.path.endsWith('/settings/employees')).options.body)
 assert.equal(saved.rows[0].rate_ca1,45000)
 assert.equal(document.querySelector('.department-config-table input').value,'45.000')
 assert.ok(![...document.querySelectorAll('button')].some(button=>button.textContent==='BẢNG 1 · LƯƠNG GIỜ'))
 const source=document.querySelector('.department-payroll-source-section')
 assert.equal(source.parentElement.classList.contains('department-payroll-config-page'),true)
 assert.equal(source.parentElement.lastElementChild,source)
 assert.equal(document.querySelectorAll('.department-config-table-section').length,2)
})

test('configuration renews an expired session before saving',async t=>{
 const f=await fixture(t,true);await f.render(h(Settings,{user:{role:'admin'}}))
 await f.change(document.querySelector('.department-config-table input'),'46.000')
 await f.click('Lưu cấu hình')
 const saves=f.requests.filter(r=>r.path.endsWith('/settings/employees'))
 assert.equal(saves.length,2)
 assert.equal(saves[1].options.headers.get('Authorization'),'Bearer renewed')
 assert.equal(JSON.parse(saves[1].options.body).rows[0].rate_ca1,46000)
 assert.match(document.body.textContent,/Đã lưu cấu hình/)
})

test('wide payroll tables fit the available width and restore full size after resizing',()=>{
 const table={parentElement:{clientWidth:800},scrollWidth:2000,style:{}}
 fitPayrollTable(table);assert.equal(table.style.zoom,'0.4')
 table.parentElement.clientWidth=2200;fitPayrollTable(table);assert.equal(table.style.zoom,'1')
 table.parentElement.clientWidth=0;fitPayrollTable(table);assert.equal(table.style.zoom,'1')
})

test('editable salary configuration stays full size even under the parent payroll fitter',()=>{
 const table={parentElement:{clientWidth:320},scrollWidth:2000,style:{zoom:'0.16'},closest:selector=>selector==='.department-config-table'?{}:null}
 fitPayrollTable(table);assert.equal(table.style.zoom,'1')
 table.parentElement.clientWidth=0;table.style.zoom='0.4';fitPayrollTable(table);assert.equal(table.style.zoom,'1')
})

test('save then reopen draft preserves edits and clears stale filters',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình')
 await f.change(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]'),'123.000');await f.click('Lưu bảng nháp')
 await f.change(document.querySelector('.department-payroll-table-search input'),'missing');await f.click('Mở bảng nháp')
 assert.equal(document.querySelectorAll('.department-payroll-table tbody tr').length,3);assert.equal(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]').value,'123.000')
})
test('deduction summary updates all rows despite visible filters',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình')
 const headers=[...document.querySelectorAll('.department-payroll-table th')].map(el=>el.textContent)
 assert.equal(headers[headers.indexOf('Ứng lương')+1],'Phạt vi phạm')
 const month=document.querySelector('.department-payroll-toolbar input[type="month"]').value
 await f.change(document.querySelector('.department-payroll-table-search input'),'Quản Lý')
 await act(()=>window.dispatchEvent(new window.CustomEvent('vera-salary-advance-summary',{detail:{month,byEmployee:{a:{payroll_total:100000}}}})))
 await f.click('Lưu bảng nháp');const saved=JSON.parse(f.requests.find(r=>r.path.endsWith('/draft')&&r.options.method==='PUT').options.body);assert.equal(saved.rows.find(r=>r.employee_username==='a').advance,100000)
})

test('payroll actions precede table and share offers prepared PNG or PDF',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình')
 const toolbar=document.querySelector('.department-payroll-top-actions'),table=document.querySelector('.department-payroll-table')
 assert.ok(toolbar.compareDocumentPosition(table)&window.Node.DOCUMENT_POSITION_FOLLOWING)
 const buttons=[...toolbar.querySelectorAll('button')];const exportIndex=buttons.findIndex(b=>b.textContent.trim()==='Xuất excel');assert.equal(buttons[exportIndex+1].textContent.trim(),'Chia sẻ')
 await f.click('Chia sẻ');assert.equal(document.querySelector('dialog[aria-label="Chia sẻ bảng lương"]').open,true);assert.ok(f.requests.some(r=>r.path.endsWith('/export.png')));assert.ok(f.requests.some(r=>r.path.endsWith('/export.pdf')))
 assert.equal([...document.querySelectorAll('button')].find(b=>b.textContent==='Ảnh PNG').disabled,false)
})

test('save image and PDF download prepared files even when native sharing is available',async t=>{
 const f=await fixture(t),downloads=[],files=[],shares=[]
 navigator.canShare=()=>true;navigator.share=async payload=>{shares.push(payload)}
 const originalCreate=URL.createObjectURL,originalRevoke=URL.revokeObjectURL
 URL.createObjectURL=file=>{files.push(file);return `blob:payroll-${files.length}`}
 URL.revokeObjectURL=()=>{}
 t.after(()=>{URL.createObjectURL=originalCreate;URL.revokeObjectURL=originalRevoke})
 window.HTMLAnchorElement.prototype.click=function(){downloads.push({name:this.download,connected:this.isConnected})}
 await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình');await f.click('Chia sẻ')
 const month=document.querySelector('.department-payroll-toolbar input[type="month"]').value
 const exportCalls=()=>f.requests.filter(r=>/\/export\.(png|pdf)$/.test(r.path)).length
 assert.equal(exportCalls(),2)
 const groups=[...document.querySelectorAll('.department-payroll-share-format')].map(group=>[...group.querySelectorAll('button')].map(button=>button.textContent.trim()))
 assert.deepEqual(groups,[['Ảnh PNG','Lưu ảnh'],['PDF','Lưu PDF']])
 await f.click('Lưu ảnh');await f.click('Lưu PDF')
 assert.deepEqual(downloads.map(item=>item.name),[`Luong_hanh_chanh_${month}.png`,`Luong_hanh_chanh_${month}.pdf`])
 assert.ok(downloads.every(item=>item.connected));assert.equal(document.querySelectorAll('a[download]').length,0)
 assert.deepEqual(files.map(file=>file.type),['image/png','application/pdf'])
 assert.equal(shares.length,0);assert.equal(exportCalls(),2)
 assert.equal(document.querySelector('dialog[aria-label="Chia sẻ bảng lương"]').open,true)
 await f.click('Ảnh PNG');assert.equal(shares.length,1);assert.equal(shares[0].files[0],files[0])
 assert.equal(document.querySelector('dialog[aria-label="Chia sẻ bảng lương"]').open,false)
})

test('delete draft confirms and removes only the draft; recalculate uses individual sources',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình');await f.click('Lưu bảng nháp')
 window.confirm=()=>false;const before=f.requests.length
 await f.click('Xóa bảng lương nháp');await f.click('Tính lại lương');assert.equal(f.requests.length,before)
 window.confirm=()=>true;await f.click('Tính lại lương')
 assert.equal(f.requests.filter(r=>r.path.endsWith('/calculate')).length,2)
 assert.ok(f.requests.filter(r=>r.path.endsWith('/calculate')).every(r=>new URL(r.url).searchParams.get('source')==='employee'))
 await f.click('Xóa bảng lương nháp');assert.ok(f.requests.some(r=>r.path.endsWith('/draft')&&r.options.method==='DELETE'))
 assert.equal(document.querySelector('.department-payroll-table'),null)
 await f.click('Mở bảng nháp');assert.match(document.body.textContent,/chưa có bảng lương nháp/)
 await f.click('Tính lương theo cấu hình');assert.equal(document.querySelectorAll('.department-payroll-table tbody tr').length,3)
})
test('draft delete is hidden without save permission',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'letan',permissions:{payroll_calculate:true}}}))
 assert.ok(![...document.querySelectorAll('button')].some(b=>b.textContent.includes('Xóa bảng lương nháp')))
})

test('employee search suggests matching names and Clear restores rows without requests',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình')
 const before=f.requests.length
 await f.change(document.querySelector('.department-payroll-table-search input'),'quan ly')
 const option=[...document.querySelectorAll('[role=option]')].find(el=>el.textContent.includes('Quản Lý B'))
 assert.ok(option);await act(()=>option.click())
 assert.equal(document.querySelectorAll('.department-payroll-table tbody tr').length,1)
 await act(()=>document.querySelector('[aria-label="Clear Tìm nhân viên"]').click())
 assert.equal(document.querySelectorAll('.department-payroll-table tbody tr').length,3)
 assert.equal(document.querySelector('[role=listbox]'),null);assert.equal(f.requests.length,before)
 assert.equal(document.querySelectorAll('td.department-payroll-net-column').length,3)
})

test('probation edits and reopening preserve reduced income and full deductions',async t=>{
 const trial={...rows[0],probation_rate:0.75,salary:162000,combo_sales:375000,total_salary:537000,net_salary:437000,advance:100000}
 const f=await fixture(t,false,[trial]);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương theo cấu hình')
 await f.change(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]'),'150.000')
 await f.click('Lưu bảng nháp');let saved=JSON.parse(f.requests.filter(r=>r.path.endsWith('/draft')&&r.options.method==='PUT').at(-1).options.body).rows[0]
 assert.equal(saved.salary,162000);assert.equal(saved.responsibility,150000);assert.equal(saved.combo_sales,375000);assert.equal(saved.advance,100000);assert.equal(saved.net_salary,587000)
 await f.click('Mở bảng nháp');await f.click('Lưu bảng nháp')
 saved=JSON.parse(f.requests.filter(r=>r.path.endsWith('/draft')&&r.options.method==='PUT').at(-1).options.body).rows[0]
 assert.equal(saved.salary,162000);assert.equal(saved.net_salary,587000)
})

const admin = { id: 'admin-a', username: 'admin-a', role: 'admin' }
const button = label => [...document.querySelectorAll('button')].find(node => node.textContent.trim() === label)
const rowCount = () => document.querySelectorAll('.department-payroll-table tbody tr').length
const monthInput = () => document.querySelector('.department-payroll-toolbar input[type="month"]')
const otherMonth = month => month === '2026-08' ? '2026-07' : '2026-08'
function deferRequest(match) {
  const original = globalThis.fetch
  let release, captured
  const gate = new Promise(resolve => { release = resolve })
  globalThis.fetch = async (url, options = {}) => {
    const response = await original(url, options)
    if (match(new URL(url), options)) { captured = options; await gate }
    return response
  }
  return { release: () => act(async () => { release(); await new Promise(resolve => setTimeout(resolve, 10)) }), captured: () => captured }
}
async function invalidatePanel(f, scope) {
  if (scope === 'month') await f.change(monthInput(), otherMonth(monthInput().value))
  if (scope === 'account') await f.render(h(Panel, { user: { ...admin, id: 'admin-b', username: 'admin-b' } }))
  if (scope === 'permission') await f.render(h(Panel, { user: { ...admin, role: 'letan', permissions: { payroll_calculate: true } } }))
  if (scope === 'unmount') await f.unmount()
}

test('both config groups expose two exclusive tick choices and save source with expected revision', async t => {
  const f = await fixture(t)
  f.data.salary_config_tables.tapvu = [{ employee_username: 'cleaner', employee_name: 'Tạp Vụ', department: 'tapvu', default_base_salary: 6000000, salary_source: 'attendance' }]
  f.data.salary_employee_catalog.push({employee_username:'cleaner',employee_name:'Tạp Vụ',department:'tapvu',salary_source:'attendance'})
  await f.render(h(Settings, { user: admin }))
  const groups = [...document.querySelectorAll('[role="radiogroup"]')]
  assert.equal(groups.length, 2)
  assert.deepEqual(groups.map(group => [...group.querySelectorAll('input')].map(input => input.checked)), [[true, false], [false, true]])
  assert.ok(groups.every(group => group.textContent.includes('Tính lương từ Thống kê') && group.textContent.includes('Tính từ Chấm công')))
  await act(() => groups[0].querySelector('[value="attendance"]').click())
  await act(() => groups[0].querySelector('[value="attendance"]').click())
  assert.deepEqual([...groups[0].querySelectorAll('input')].map(input => input.checked), [false, true])
  await f.click('Lưu cấu hình')
  const saved = JSON.parse(f.requests.find(r => r.path.endsWith('/settings/employees')).options.body)
  assert.equal(saved.expected_revision, 1)
  assert.deepEqual(saved.salary_sources.map(row => row.salary_source), ['attendance', 'attendance'])
  assert.equal(saved.rows, undefined)
  await f.click('Lưu cấu hình')
  assert.equal(JSON.parse(f.requests.filter(r => r.path.endsWith('/settings/employees')).at(-1).options.body).expected_revision, 2)
})

test('configuration controls remain read-only for non-admin and admin denied config permission', async t => {
  const f = await fixture(t)
  for (const user of [{ role: 'letan', permissions: { payroll_config_edit: true } }, { ...admin, permissions: { payroll_config_edit: false } }]) {
    await f.render(h(Settings, { user }))
    assert.ok([...document.querySelectorAll('.department-config-table input')].every(input => input.disabled))
    assert.equal(button('Lưu cấu hình'), undefined)
  }
  assert.equal(f.requests.some(r => r.path.endsWith('/settings/employees')), false)
})

test('conflicting config save keeps unsaved source and does not silently adopt a new revision', async t => {
  const f = await fixture(t); await f.render(h(Settings, { user: admin }))
  await act(() => document.querySelector('[value="attendance"]').click())
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => new URL(url).pathname.endsWith('/settings/employees')
    ? new Response(JSON.stringify({ detail: 'Cấu hình đã thay đổi. Hãy làm mới.' }), { status: 409 }) : original(url, options)
  await f.click('Lưu cấu hình')
  assert.equal(document.querySelector('[value="attendance"]').checked, true)
  assert.match(document.body.textContent, /Cấu hình đã thay đổi/)
})

test('mixed roster keeps individual sources and opaque provenance through edit, draft and export', async t => {
  const mixed = rows.map((row, i) => ({ ...row, calculation_source: i === 1 ? 'attendance' : 'schedule', calculation_snapshot: { proof: `opaque-${i}`, source: i === 1 ? 'attendance' : 'schedule' } }))
  const f = await fixture(t, false, mixed); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  assert.equal(rowCount(), 3)
  assert.equal(new URL(f.requests.find(r => r.path.endsWith('/calculate')).url).searchParams.get('source'), 'employee')
  assert.match(document.querySelector('.department-payroll-table').textContent, /Nguồn lương: Thống kê/)
  assert.match(document.querySelector('.department-payroll-table').textContent, /Nguồn lương: Chấm công/)
  await f.change(document.querySelector('[aria-label="Trách nhiệm Quản Lý B"]'), '123.000')
  await f.click('Lưu bảng nháp'); await f.click('Mở bảng nháp')
  window.HTMLAnchorElement.prototype.click = () => {}
  await f.click('Xuất excel')
  for (const request of f.requests.filter(r => (r.path.endsWith('/draft') && r.options.method === 'PUT') || r.path.endsWith('/export.xlsx'))) {
    const saved = JSON.parse(request.options.body).rows
    assert.deepEqual(saved.map(row => row.calculation_source), mixed.map(row => row.calculation_source))
    assert.deepEqual(saved.map(row => row.calculation_snapshot), mixed.map(row => row.calculation_snapshot))
  }
})

for (const pending of ['attendance_pending', 'configuration_pending']) test(`${pending} blocks payroll outputs and keeps pending totals after edits`, async t => {
  const f = await fixture(t, false, [{ ...rows[0], [pending]: true, salary: null, total_salary: null, net_salary: null }])
  await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  assert.equal(button('Hoàn thành bảng lương').disabled, true)
  assert.equal(button('Xuất excel').disabled, true); assert.equal(button('Chia sẻ').disabled, true)
  assert.equal(document.querySelector('[aria-label="Chọn gửi email Nhân Viên A"]').disabled, true)
  assert.match(document.querySelector('.department-payroll-summary').textContent, /Chờ đủ dữ liệu/)
  await f.change(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]'), '100.000')
  await f.click('Lưu bảng nháp')
  const saved = JSON.parse(f.requests.find(r => r.path.endsWith('/draft') && r.options.method === 'PUT').options.body).rows[0]
  assert.equal(saved.net_salary, null); assert.equal(saved[pending], true)
  assert.match(document.querySelector('.department-payroll-table').textContent, pending === 'configuration_pending' ? /Chờ cấu hình ca\/đơn giá/ : /Chờ xác nhận công/)
})

for (const action of ['calculate', 'draft-load', 'export']) {
  for (const scope of ['month', 'account', 'permission', 'unmount']) test(`${action} ignores stale response after ${scope} changes`, async t => {
    const f = await fixture(t); await f.render(h(Panel, { user: admin }))
    if (action !== 'calculate') await f.click('Tính lương theo cấu hình')
    if (action === 'draft-load') await f.click('Lưu bảng nháp')
    const originalMonth = monthInput().value
    let downloads = 0; window.HTMLAnchorElement.prototype.click = () => { downloads++ }
    window.confirm = () => true
    const matches = (url, options) => action === 'calculate' ? url.pathname.endsWith('/calculate')
      : action === 'draft-load' ? url.pathname.endsWith('/draft') && !options.method
      : action === 'draft-save' ? url.pathname.endsWith('/draft') && options.method === 'PUT'
      : action === 'export' ? url.pathname.endsWith('/export.xlsx') : url.pathname.endsWith('/complete')
    const gate = deferRequest(matches)
    const labels = { calculate: 'Tính lương theo cấu hình', 'draft-load': 'Mở bảng nháp', 'draft-save': 'Lưu bảng nháp', export: 'Xuất excel', complete: 'Hoàn thành bảng lương' }
    await f.click(labels[action]); assert.ok(gate.captured())
    await invalidatePanel(f, scope)
    assert.equal(gate.captured().signal.aborted, true)
    const historyReads = f.requests.filter(r => r.path.endsWith('/history')).length
    await gate.release()
    assert.equal(rowCount(), 0); assert.equal(downloads, 0)
    assert.equal(f.requests.filter(r => r.path.endsWith('/history')).length, historyReads)
    if (action === 'draft-save' || action === 'complete') assert.equal(JSON.parse(gate.captured().body).month, originalMonth)
    if (scope === 'month') {
      assert.equal(monthInput().value, otherMonth(originalMonth))
      assert.equal(button('Lưu bảng nháp'), undefined)
      assert.doesNotMatch(document.body.textContent, /Đã tính lương nháp|Đã mở bảng Lương|Đã hoàn thành/)
    }
  })
}

for (const action of ['Tính lại lương', 'Hoàn thành bảng lương', 'Xóa bảng lương nháp']) {
  for (const scope of ['month', 'account', 'permission', 'unmount']) test(`${action} confirmation cannot act after ${scope} changes`, async t => {
    const f = await fixture(t); f.manualDialogs()
    await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
    const calls = f.requests.filter(r => r.path.endsWith('/calculate') || r.options.method === 'POST' || r.options.method === 'DELETE').length
    await f.click(action)
    const confirm = document.querySelector('dialog[data-system-dialog="confirm"] .primary-button')
    assert.ok(confirm)
    await invalidatePanel(f, scope)
    assert.equal(confirm.isConnected, false)
    await act(() => confirm.click())
    assert.equal(f.requests.filter(r => r.path.endsWith('/calculate') || r.options.method === 'POST' || r.options.method === 'DELETE').length, calls)
  })
}

for (const action of ['Tính lại lương', 'Hoàn thành bảng lương', 'Xóa bảng lương nháp']) test(`${action} cancel leaves payroll unchanged without writes`, async t => {
  const f = await fixture(t); f.manualDialogs()
  await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  const count = f.requests.length
  await f.click(action); await act(() => document.querySelector('dialog[data-system-dialog="confirm"] .secondary-button').click())
  assert.equal(f.requests.length, count); assert.equal(rowCount(), 3)
})

test('snapshot revision change while confirmation is open cancels completion', async t => {
  const f = await fixture(t); f.manualDialogs()
  await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  await f.click('Hoàn thành bảng lương')
  await act(() => window.dispatchEvent(new window.CustomEvent('vera-salary-advance-summary', { detail: { month: monthInput().value, byEmployee: { a: { payroll_total: 100000 } } } })))
  assert.equal(document.querySelector('dialog[data-system-dialog="confirm"]'), null)
  assert.equal(f.requests.some(r => r.path.endsWith('/complete')), false)
})

test('late save response cannot overwrite a newer advance revision', async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  const gate = deferRequest((url, options) => url.pathname.endsWith('/draft') && options.method === 'PUT')
  await f.click('Lưu bảng nháp')
  await act(() => window.dispatchEvent(new window.CustomEvent('vera-salary-advance-summary', { detail: { month: monthInput().value, byEmployee: { a: { payroll_total: 100000 } } } })))
  assert.equal(gate.captured().signal?.aborted || false, false)
  assert.equal(document.querySelector('[data-ui-key="u-d8d128bf8ea0"]').disabled, true)
  await gate.release()
  assert.equal(document.querySelector('[aria-label="Ứng lương Nhân Viên A"]').value, '100.000')
  assert.equal(button('Lưu bảng nháp').disabled, false)
})

for (const scope of ['month', 'account', 'permission', 'unmount', 'cancel', 'filter']) test(`prepared shares are discarded after ${scope}`, async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  const gate = deferRequest(url => /\/export\.(png|pdf)$/.test(url.pathname))
  let downloads = 0; window.HTMLAnchorElement.prototype.click = () => { downloads++ }
  await f.click('Chia sẻ'); assert.ok(gate.captured())
  if (scope === 'cancel') await f.click('Đóng')
  else if (scope === 'filter') await f.change(document.querySelector('.department-payroll-department-filter select'), 'letan')
  else await invalidatePanel(f, scope)
  assert.equal(gate.captured().signal.aborted, true)
  await gate.release()
  assert.notEqual(document.querySelector('dialog[aria-label="Chia sẻ bảng lương"]')?.open, true)
  assert.equal(downloads, 0)
  if (button('Lưu ảnh')) assert.equal(button('Lưu ảnh').disabled, true)
})

test('completed share files cannot be downloaded after changing the payroll filter', async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình'); await f.click('Chia sẻ')
  const download = button('Lưu ảnh'); assert.equal(download.disabled, false)
  let downloads = 0; window.HTMLAnchorElement.prototype.click = () => { downloads++ }
  await f.change(document.querySelector('.department-payroll-department-filter select'), 'letan')
  await act(() => download.click())
  assert.equal(downloads, 0)
})

test('approved late preview keeps missed time unpaid and only subtracts the remaining fine', async t => {
  const late = { ...rows[0], hours_ca1: 7, salary: 189000, total_salary: 689000, net_salary: 666000, late_penalty: 50000, late_penalty_credit: 27000, effective_late_penalty: 23000, unpaid_late_wage: 27000 }
  const f = await fixture(t, false, [late]); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  assert.match(document.querySelector('.department-payroll-late-credit').textContent, /Lương thời gian trễ không được tính: 27\.000đ · Phạt trễ trừ thêm: 23\.000đ/)
  await f.change(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]'), '100.000')
  await f.click('Lưu bảng nháp')
  const saved = JSON.parse(f.requests.find(r => r.path.endsWith('/draft') && r.options.method === 'PUT').options.body).rows[0]
  assert.equal(saved.hours_ca1, 7); assert.equal(saved.salary, 189000)
  assert.equal(saved.late_penalty, 50000); assert.equal(saved.effective_late_penalty, 23000)
  assert.equal(saved.net_salary, 766000)
})

for (const scope of ['account', 'permission', 'unmount']) test(`configuration save response cannot cross ${scope} scope`, async t => {
  const f = await fixture(t); await f.render(h(Settings, { user: admin }))
  await act(() => document.querySelector('[value="attendance"]').click())
  const gate = deferRequest(url => url.pathname.endsWith('/settings/employees'))
  await f.click('Lưu cấu hình'); assert.ok(gate.captured())
  if (scope === 'unmount') await f.unmount()
  else await f.render(h(Settings, { user: scope === 'account' ? { ...admin, id: 'admin-b' } : { ...admin, permissions: { payroll_config_edit: false } } }))
  assert.equal(gate.captured().signal, undefined)
  if (scope !== 'unmount') assert.ok([...document.querySelectorAll('.department-config-table input')].every(input => input.disabled))
  await gate.release()
  assert.doesNotMatch(document.body.textContent, /Đã lưu cấu hình/)
  if (scope !== 'unmount') assert.equal(document.querySelector('[value="schedule"]').checked, true)
})

test('a late old calculation cannot clear the new month request busy state', async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin }))
  const oldMonth = monthInput().value
  const oldGate = deferRequest(url => url.pathname.endsWith('/calculate') && url.searchParams.get('month') === oldMonth)
  await f.click('Tính lương theo cấu hình')
  await f.change(monthInput(), otherMonth(oldMonth))
  const newGate = deferRequest(url => url.pathname.endsWith('/calculate') && url.searchParams.get('month') !== oldMonth)
  await f.click('Tính lương theo cấu hình')
  await oldGate.release()
  assert.equal(button('Tính lương theo cấu hình').disabled, true); assert.equal(rowCount(), 0)
  await newGate.release()
  assert.equal(button('Tính lương theo cấu hình').disabled, false); assert.equal(rowCount(), 3)
  await f.click('Lưu bảng nháp')
  assert.equal(JSON.parse(f.requests.find(r => r.path.endsWith('/draft') && r.options.method === 'PUT').options.body).month, otherMonth(oldMonth))
})

test('history open mutation is locked until its outcome is established', async t => {
  const f = await fixture(t)
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    const path = new URL(url).pathname
    if (path.endsWith('/history')) return new Response(JSON.stringify({ items: [{ id: 'h-old', month: '2026-07', month_label: '07/2026', employee_count: 3 }] }))
    if (path.endsWith('/h-old/open')) return new Response(JSON.stringify({ month: '2026-07', rows, draft_revision: 1, history_revision: 0, history_id: 'h-old', message: 'Opened old history' }))
    return original(url, options)
  }
  await f.render(h(Panel, { user: admin })); await f.click('Hiện lịch sử')
  const gate = deferRequest(url => url.pathname.endsWith('/h-old/open'))
  await f.click('Mở để sửa')
  const originalMonth = monthInput().value
  assert.equal(monthInput().disabled, true)
  await f.change(monthInput(), otherMonth(originalMonth))
  assert.equal(monthInput().value, originalMonth)
  await gate.release()
  assert.equal(monthInput().value, '2026-07'); assert.equal(rowCount(), 3)
  assert.match(document.body.textContent, /Opened old history/)
})

test('source choices cover unconfigured HC roster and filtered saves never materialize inherited rates', async t => {
  const f = await fixture(t)
  f.data.salary_employee_catalog.push(
    { employee_username: 'b', employee_name: 'Quản Lý B', department: 'quanly', department_label: 'Quản lý', salary_source: 'attendance' },
    { employee_username: 'c', employee_name: 'Nhân Viên C', department: 'support', department_label: 'Hỗ trợ' })
  await f.render(h(Settings, { user: admin }))
  assert.equal(document.querySelectorAll('[role="radiogroup"]').length, 3)
  assert.equal(document.querySelectorAll('.department-config-table tbody tr').length, 1)
  await act(() => document.querySelector('[name="salary-source-c"][value="attendance"]').click())
  await f.change(document.querySelector('[aria-label="Tìm cấu hình nguồn lương"]'), 'Quản Lý')
  assert.equal(document.querySelectorAll('[role="radiogroup"]').length, 1)
  await f.click('Lưu cấu hình')
  const saved = JSON.parse(f.requests.find(r => r.path.endsWith('/settings/employees')).options.body)
  assert.deepEqual(saved.salary_sources, [
    { employee_username: 'a', salary_source: 'schedule' },
    { employee_username: 'b', salary_source: 'attendance' },
    { employee_username: 'c', salary_source: 'attendance' },
  ])
  assert.equal(saved.rows, undefined)
  assert.equal(saved.salary_sources.some(row => 'rate_ca1' in row || 'default_base_salary' in row), false)
})

test('source identities stack display and full names; long custom departments stay searchable and labels select exclusively', async t => {
  const f = await fixture(t)
  f.data.salary_employee_catalog = [
    { employee_username: 'Gia Anh', employee_name: 'Nguyễn Gia Anh', department: 'letan', department_label: 'Lễ tân', salary_source: 'schedule' },
    { employee_username: 'TênHiểnThịRấtDàiKhôngCóKhoảngTrắng', employee_name: 'Nguyễn Thị Tên Đầy Đủ Nhiều Thành Phần', department: 'custom', department_label: 'Bộ phận hành chánh mở rộng với tên rất dài', salary_source: 'attendance' },
  ]
  await f.render(h(Settings, { user: admin }))
  const table = document.querySelector('.department-payroll-source-table table')
  assert.equal(table.querySelectorAll('colgroup col').length, 3)
  assert.equal(table.querySelectorAll('th[scope="col"]').length, 3)
  const identities = [...table.querySelectorAll('.department-payroll-source-identity')]
  assert.deepEqual([...identities[0].children].map(node => [node.tagName, node.textContent]), [['STRONG', 'Gia Anh'], ['SMALL', 'Nguyễn Gia Anh']])
  assert.equal(identities[1].querySelector('small').textContent, f.data.salary_employee_catalog[1].employee_name)
  const groups = [...table.querySelectorAll('[role="radiogroup"]')]
  assert.equal(groups[0].getAttribute('aria-label'), 'Nguồn lương Nguyễn Gia Anh')
  assert.deepEqual([...groups[0].querySelectorAll('label>span')].map(node => node.textContent), ['Tính lương từ Thống kê', 'Tính từ Chấm công'])
  const radios = [...groups[0].querySelectorAll('input')]
  assert.ok(radios.every(node => node.type === 'radio' && node.name === 'salary-source-Gia Anh' && !node.disabled))
  radios[1].focus(); assert.equal(document.activeElement, radios[1])
  await act(() => radios[1].closest('label').click())
  assert.deepEqual(radios.map(node => node.checked), [false, true])
  assert.equal(groups[1].querySelector('input[value="attendance"]').checked, true)
  await f.change(document.querySelector('[aria-label="Tìm cấu hình nguồn lương"]'), 'hanh chanh mo rong')
  assert.equal(table.querySelectorAll('tbody tr').length, 1)
  assert.equal(table.querySelector('.department-payroll-source-identity strong').textContent, f.data.salary_employee_catalog[1].employee_username)
  await f.change(document.querySelector('[aria-label="Tìm cấu hình nguồn lương"]'), 'Nguyễn Gia Anh')
  assert.equal(table.querySelectorAll('tbody tr').length, 1)
  assert.equal(table.querySelector('input[value="attendance"]').checked, true)
  assert.equal(f.requests.filter(item => item.options.method && item.options.method !== 'GET').length, 0)
})

test('same-role canonical employee_username change clears old account payroll', async t => {
  const f = await fixture(t)
  await f.render(h(Panel, { user: { employee_username: 'admin-a', role: 'admin' } })); await f.click('Tính lương theo cấu hình')
  assert.equal(rowCount(), 3)
  await f.render(h(Panel, { user: { employee_username: 'admin-b', role: 'admin' } }))
  assert.equal(rowCount(), 0)
})

test('draft save and completion carry current draft/history revisions', async t => {
  const f = await fixture(t); window.confirm = () => true
  await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  await f.click('Lưu bảng nháp'); await f.click('Lưu bảng nháp'); await f.click('Hoàn thành bảng lương')
  const saves = f.requests.filter(r => r.path.endsWith('/draft') && r.options.method === 'PUT').map(r => JSON.parse(r.options.body))
  assert.deepEqual(saves.map(body => body.expected_revision), [0, 1])
  const complete = JSON.parse(f.requests.find(r => r.path.endsWith('/complete')).options.body)
  assert.equal(complete.expected_revision, 2); assert.equal(complete.expected_history_revision, 0)
  await f.click('Lưu bảng nháp')
  const latest = JSON.parse(f.requests.filter(r => r.path.endsWith('/draft') && r.options.method === 'PUT').at(-1).options.body)
  assert.equal(latest.expected_revision, 3); assert.equal(latest.expected_history_revision, 1)
})

for (const action of ['Lưu bảng nháp', 'Hoàn thành bảng lương']) test(`${action} keeps a write barrier while response is unresolved`, async t => {
  const f = await fixture(t); window.confirm = () => true
  await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  const gate = deferRequest((url, options) => action === 'Lưu bảng nháp' ? url.pathname.endsWith('/draft') && options.method === 'PUT' : url.pathname.endsWith('/complete'))
  const originalMonth = monthInput().value
  await f.click(action)
  const save = document.querySelector('[data-ui-key="u-d8d128bf8ea0"]')
  assert.equal(monthInput().disabled, true); assert.equal(save.disabled, true)
  assert.equal(document.querySelector('.department-payroll-table-search input').disabled, true)
  assert.equal(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]').disabled, true)
  await f.change(monthInput(), otherMonth(originalMonth))
  await f.change(document.querySelector('.department-payroll-table-search input'), 'missing')
  assert.equal(monthInput().value, originalMonth); assert.equal(rowCount(), 3)
  assert.equal(gate.captured().signal?.aborted || false, false)
  await gate.release(); assert.equal(monthInput().disabled, false)
})

for (const scope of ['account', 'permission', 'unmount']) test(`sent save does not update stale ${scope} view and keeps settlement tracking`, async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  const gate = deferRequest((url, options) => url.pathname.endsWith('/draft') && options.method === 'PUT')
  await f.click('Lưu bảng nháp'); await invalidatePanel(f, scope)
  assert.equal(gate.captured().signal?.aborted || false, false)
  if (scope !== 'unmount') assert.equal(monthInput().disabled, true)
  await gate.release(); assert.equal(rowCount(), 0)
  assert.doesNotMatch(document.body.textContent, /Đã lưu/)
  if (scope !== 'unmount') assert.equal(monthInput().disabled, false)
})

for (const failure of ['conflict', 'unknown']) test(`${failure} save outcome blocks repeat write until explicit draft reload`, async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình'); await f.click('Lưu bảng nháp')
  await f.change(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]'), '123.000')
  const original = globalThis.fetch; let calls = 0
  globalThis.fetch = async (url, options) => {
    if (new URL(url).pathname.endsWith('/draft') && options?.method === 'PUT') {
      calls++
      if (failure === 'conflict') return new Response(JSON.stringify({ detail: 'Phiên bản bảng lương đã thay đổi.' }), { status: 409 })
      await original(url, options); throw new Error('Response disconnected after commit')
    }
    return original(url, options)
  }
  await f.click('Lưu bảng nháp')
  assert.equal(button('Lưu bảng nháp').disabled, true); assert.match(document.body.textContent, /trước khi lưu tiếp/)
  await f.click('Lưu bảng nháp'); assert.equal(calls, 1)
  await f.click('Mở bảng nháp'); assert.equal(button('Lưu bảng nháp').disabled, false)
  assert.equal(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]').value, failure === 'unknown' ? '123.000' : '')
})

test('history identity and saved source survive open, draft save, reopen and export', async t => {
  const historical = rows.map(row => ({ ...row, calculation_source: 'attendance', calculation_snapshot: { source: 'attendance', proof: 'saved-history' } }))
  const f = await fixture(t), original = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    const path = new URL(url).pathname
    if (path.endsWith('/history')) return new Response(JSON.stringify({ items: [{ id: 'h-saved', month: '2026-07', month_label: '07/2026', employee_count: 3 }], history_revision: 4 }))
    if (path.endsWith('/h-saved/open')) return new Response(JSON.stringify({ month: '2026-07', rows: historical, draft_revision: 1, history_revision: 4, history_id: 'h-saved', message: 'Opened saved history' }))
    return original(url, options)
  }
  await f.render(h(Panel, { user: admin })); await f.click('Hiện lịch sử'); await f.click('Mở để sửa')
  await f.click('Lưu bảng nháp'); await f.click('Mở bảng nháp')
  f.data.salary_employee_catalog[0].salary_source = 'schedule'
  window.HTMLAnchorElement.prototype.click = () => {}
  await f.click('Xuất excel')
  const exported = JSON.parse(f.requests.find(r => r.path.endsWith('/export.xlsx')).options.body)
  assert.equal(exported.history_id, 'h-saved')
  assert.ok(exported.rows.every(row => row.calculation_source === 'attendance' && row.calculation_snapshot.proof === 'saved-history'))
})

test('editable full-roster source ticks remain full size on narrow and hidden containers', () => {
  const table = { parentElement: { clientWidth: 320 }, scrollWidth: 900, style: { zoom: '0.35' }, closest: selector => selector === '.department-payroll-source-table' ? {} : null }
  fitPayrollTable(table); assert.equal(table.style.zoom, '1')
  table.parentElement.clientWidth = 0; table.style.zoom = '0.35'
  fitPayrollTable(table); assert.equal(table.style.zoom, '1')
})

for (const mode of ['old-backend', 'missing-capability', 'missing-revision', 'future-contract']) test(`version gate keeps ${mode} payroll read-only and blocks all unsafe calls`, async t => {
  const f = await fixture(t)
  if (mode === 'old-backend' || mode === 'missing-capability') delete f.data.hc_payroll_contract
  if (mode === 'old-backend' || mode === 'missing-revision') delete f.data.employee_config_revision
  if (mode === 'future-contract') f.data.hc_payroll_contract = 2
  const original = globalThis.fetch
  globalThis.fetch = async (url, options) => {
    if (new URL(url).pathname.endsWith('/draft') && !options?.method) return new Response(JSON.stringify({ month: new URL(url).searchParams.get('month'), rows }))
    return original(url, options)
  }
  await f.render(h(Panel, { user: admin }))
  assert.match(document.querySelector('.department-payroll-backend-required').textContent, /Cần cập nhật máy chủ/)
  assert.equal(button('Tính lương theo cấu hình').disabled, true)
  assert.equal(button('Xóa bảng lương nháp').disabled, true)
  await f.click('Tính lương theo cấu hình'); await f.click('Xóa bảng lương nháp')
  await f.click('Mở bảng nháp'); assert.equal(rowCount(), 3)
  for (const label of ['Lưu bảng nháp', 'Hoàn thành bảng lương', 'Xuất excel', 'Chia sẻ']) assert.equal(button(label).disabled, true)
  assert.equal(document.querySelector('[aria-label="Trách nhiệm Nhân Viên A"]').disabled, true)
  assert.equal(document.querySelector('[aria-label="Chọn gửi email Nhân Viên A"]').disabled, true)
  for (const label of ['Lưu bảng nháp', 'Hoàn thành bảng lương', 'Xuất excel', 'Chia sẻ']) await f.click(label)
  assert.equal(f.requests.some(r => r.options.method && r.options.method !== 'GET'), false)
  assert.equal(f.requests.some(r => r.path.endsWith('/calculate')), false)
  await f.render(h(Settings, { user: admin }))
  assert.equal(button('Lưu cấu hình').disabled, true)
  assert.ok([...document.querySelectorAll('.department-config-table input, .department-payroll-source-table input')].every(input => input.disabled))
  await f.click('Lưu cấu hình'); assert.equal(f.requests.some(r => r.path.endsWith('/settings/employees')), false)
})

test('matched backend uses only versioned calculate, write, export and email routes', async t => {
  const f = await fixture(t); window.confirm = () => true; window.HTMLAnchorElement.prototype.click = () => {}
  await f.render(h(Panel, { user: admin })); assert.equal(document.querySelector('.department-payroll-backend-required'), null)
  await f.click('Tính lương theo cấu hình'); await f.click('Lưu bảng nháp'); await f.click('Xuất excel')
  await act(() => document.querySelector('[aria-label="Chọn gửi email Nhân Viên A"]').click())
  await f.click('Gửi email (1)'); await f.click('Hoàn thành bảng lương')
  for (const request of f.requests.filter(r => r.options.method || r.path.endsWith('/calculate'))) assert.match(request.path, /^\/v2\/department-payroll-v2\//)
  await f.render(h(Settings, { user: admin })); await act(() => document.querySelector('[value="attendance"]').click()); await f.click('Lưu cấu hình')
  assert.equal(f.requests.filter(r => r.path.endsWith('/settings/employees')).at(-1).path, '/v2/department-payroll-v2/settings/employees')
})

test('cached new capability cannot fall back to destructive legacy source save after backend rollback', async t => {
  const f = await fixture(t); await f.render(h(Settings, { user: admin }))
  await act(() => document.querySelector('[value="attendance"]').click())
  const original = globalThis.fetch, attempted = []; let legacyWrites = 0
  globalThis.fetch = async (url, options) => {
    const path = new URL(url).pathname
    if (options?.method === 'PUT') {
      attempted.push(path)
      if (path.startsWith('/v2/department-payroll-v2/')) return new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 })
      legacyWrites++
    }
    return original(url, options)
  }
  await f.click('Lưu cấu hình')
  assert.deepEqual(attempted, ['/v2/department-payroll-v2/settings/employees']); assert.equal(legacyWrites, 0)
  assert.match(document.querySelector('.department-payroll-backend-required').textContent, /Cần cập nhật máy chủ/)
  assert.equal(button('Lưu cấu hình').disabled, true)
  assert.equal(document.querySelector('[value="attendance"]').checked, true)
  assert.equal(document.querySelector('[value="attendance"]').disabled, true)
  globalThis.fetch = original
  await f.click('Làm mới'); assert.equal(button('Lưu cấu hình').disabled, false)
  assert.equal(document.querySelector('.department-payroll-backend-required'), null)
})

test('cached new capability cannot send legacy payroll writes after backend rollback', async t => {
  const f = await fixture(t); await f.render(h(Panel, { user: admin })); await f.click('Tính lương theo cấu hình')
  const original = globalThis.fetch, attempted = []
  globalThis.fetch = async (url, options) => {
    if (options?.method === 'PUT') { attempted.push(new URL(url).pathname); return new Response(JSON.stringify({ detail: 'Not Found' }), { status: 404 }) }
    return original(url, options)
  }
  await f.click('Lưu bảng nháp')
  assert.deepEqual(attempted, ['/v2/department-payroll-v2/combined/draft'])
  assert.equal(button('Lưu bảng nháp').disabled, true); assert.equal(button('Xuất excel').disabled, true)
  assert.match(document.querySelector('.department-payroll-backend-required').textContent, /Cần cập nhật máy chủ/)
  assert.equal(rowCount(), 3)
})
