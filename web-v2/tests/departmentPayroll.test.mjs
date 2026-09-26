import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React,{act} from 'react'
import {JSDOM} from 'jsdom'
const bootstrap=new JSDOM('<body/>');globalThis.window=bootstrap.window;globalThis.document=bootstrap.window.document;after(()=>bootstrap.window.close())
const built=await build({stdin:{contents:`export {default as Panel} from './src/pages/DepartmentPayrollPanel';export {default as Settings} from './src/pages/DepartmentPayrollSettingsPage';export {default as Tabs} from './src/components/PayrollTabs';export {recoverablePage} from './src/lib/recoverablePage'`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"})'}))}}]})
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
const {Panel,Settings,Tabs,recoverablePage}=mod.exports,h=React.createElement
const config={calculation_mode:'hourly',rate_ca1:27000,rate_ca2_before_22:30000,rate_ca2_after_22:33000}
const rows=[['a','Nhân Viên A','letan','Lễ tân',500000],['b','Quản Lý B','quanly','Quản lý',300000],['c','Nhân Viên C','letan','Lễ tân',0]].map(([id,name,dep,label,combo],i)=>({employee_username:id,employee_name:name,email:`${id}@example.test`,department:dep,department_label:label,tt:i+1,work_days:1,hours_ca1:8,combo_sales:combo,salary:216000,total_salary:216000+combo,net_salary:216000+combo,calculation_config:config,calculation_source:'schedule'}))
async function fixture(t){
 const dom=new JSDOM('<body><div id="root"/></body>',{url:'https://example.test',pretendToBeVisual:true}),requests=[]
 const data={departments:{letan:{department_label:'Lễ tân',config},quanly:{department_label:'Quản lý',config},tapvu:{department_label:'Tạp vụ',config:{calculation_mode:'monthly'}}},salary_config_tables:{operations:[{employee_username:'a',employee_name:'Nhân Viên A',department:'letan',department_label:'Lễ tân',...config}],tapvu:[]},salary_employee_catalog:[]}
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,fetch:async(url,options={})=>{
  const path=new URL(url).pathname;requests.push({path,options})
  const body=path.endsWith('/settings')?data:path.endsWith('/history')?{items:[]}:path.endsWith('/calculate')?{rows,start:'2026-09-01',end:'2026-09-26',source_label:'Lịch làm việc'}:path.endsWith('/draft')?{rows:JSON.parse(options.body).rows,message:'Đã lưu'}:{}
  return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
 }}
 const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]));for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}})
 return{requests,render:element=>act(async()=>root.render(element)),click:async label=>{const b=[...document.querySelectorAll('button')].find(b=>b.textContent.trim()===label);assert.ok(b,label);await act(async()=>b.click())},change:async(node,value)=>act(async()=>{Object.getOwnPropertyDescriptor(node.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event(node.tagName==='SELECT'?'change':'input',{bubbles:true}))})}
}
test('filters combine without requests or lost edits; save keeps the full payroll',async t=>{
 const f=await fixture(t);await f.render(h(Panel,{user:{role:'admin'}}));await f.click('Tính lương nháp từ Thống kê tháng')
 const count=()=>document.querySelectorAll('.department-payroll-table tbody tr').length
 assert.equal(count(),3)
 const search=document.querySelector('.department-payroll-filters input'),department=document.querySelector('.department-payroll-filters select'),calls=f.requests.length
 await f.change(search,'nhan vien');assert.equal(count(),2)
 await f.change(department,'quanly');assert.equal(count(),0)
 await f.change(search,'');assert.equal(count(),1)
 assert.match(document.querySelector('.department-payroll-summary').textContent,/516\.000đ/);assert.equal(f.requests.length,calls)
 await f.change(document.querySelector('[aria-label="Trách nhiệm Quản Lý B"]'),'123.000')
 await f.change(department,'letan');await f.change(department,'quanly')
 assert.equal(document.querySelector('[aria-label="Trách nhiệm Quản Lý B"]').value,'123.000')
 window.HTMLAnchorElement.prototype.click=()=>{}
 await f.click('Export Excel')
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
