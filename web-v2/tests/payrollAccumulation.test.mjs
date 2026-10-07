import test from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React,{act} from 'react'
import {JSDOM} from 'jsdom'
import {accumulationRows,filterAccumulationRows} from '../src/lib/payrollAccumulationRows.js'

test('personal accumulation periods stay closed until opened and omit zero-only payroll periods',async()=>{
 const built=await build({stdin:{contents:`import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Page from './src/pages/PayrollPersonalTracking';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=()=>root.render(<Page user={{role:'nhanvien'}} standalone/>);window.unmount=()=>root.unmount();`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"})'}))}}]})
 const dom=new JSDOM('<div id="root"/>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window
 w.IS_REACT_ACT_ENVIRONMENT=true;w.Headers=Headers
 w.MessageChannel=class{constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 w.fetch=async()=>({ok:true,json:async()=>({employees:[{employee_name:'A',role:'nhanvien',completed:true,remaining:0,periods:[{batch:'Không phát sinh',contribution:0,refund:0},{batch:'Đã đóng',contribution:500000,refund:0},{batch:'Hoàn trả',contribution:0,refund:500000}]}]})})
 w.eval(built.outputFiles[0].text)
 try {
  await w.act(async()=>w.mount())
  const toggle=()=>w.document.querySelector('.payroll-personal-section-title button')
  assert.equal(toggle().getAttribute('aria-expanded'),'false')
  assert.equal(w.document.querySelector('.payroll-personal-table'),null)
  await w.act(async()=>toggle().click())
  assert.equal(w.document.querySelectorAll('.payroll-personal-table tbody tr').length,2)
  assert.doesNotMatch(w.document.body.textContent,/Không phát sinh/)
  assert.match(w.document.body.textContent,/Đã đóng/);assert.match(w.document.body.textContent,/Hoàn trả/)
  await w.act(async()=>toggle().click())
  assert.equal(w.document.querySelector('.payroll-personal-table'),null)
 }finally{await w.act(async()=>w.unmount());w.close()}
})

test('accumulation tab follows history and combines completed, active and former staff in one table',async t=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true}),requests=[],NativeDate=Date
  const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,
  Date:class extends NativeDate{constructor(...args){super(...(args.length?args:['2026-09-30T09:00:00Z']))}},
  fetch:async url=>{
   const u=new URL(url);requests.push(u)
   const employees=[{employee_name:'A',role:'nhanvien',target:1000000,paid_total:200000,remaining:800000,periods:[{batch:'Kỳ cũ',start:'2026-08-01',end:'2026-08-15',refund:100000}]},{employee_name:'B',role:'leader',target:1000000,paid_total:1000000,remaining:0,completed:true,periods:[]}]
   const body=u.pathname.endsWith('/personal-tracking')?{employees}:u.pathname.endsWith('/accumulation-refunds')?{employees:[{employee_name:'C',employment_status:'Đã nghỉ việc'}],refunds:[{id:'r1',employee_name:'C',amount:500000,start:'2026-09-16',end:'2026-09-30',note:'Hoàn trả'}]}:u.pathname.endsWith('/history')?{records:[],batches:[],employees:[]}:{}
   return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
  }}
 const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 let root
 t.after(async()=>{if(root)await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}})
 const built=await build({stdin:{contents:`import React,{useState} from 'react';import Page from './src/pages/PayrollPageEnhanced';export default function Wrapper({user}){const [tab,setTab]=useState('calculate');return <Page user={user} activeTab={tab} onTabChange={setTab}/>}`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"});export const isSupabaseConfigured=false;export const refreshCurrentSession=getCurrentSession;export const supabase=null'}))}}]})
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const {createRoot}=await import('react-dom/client');root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(mod.exports.default,{user:{role:'admin'}})))
 const tabs=[...document.querySelectorAll('[role="tab"]')]
 assert.deepEqual(tabs.map(tab=>tab.textContent.trim()),['Tính lương','Lịch sử bảng lương','Tích lũy & Hoàn trả'])
 assert.equal(document.querySelector('[aria-label="Tích lũy và hoàn trả nhân viên"]'),null)
 await act(async()=>tabs[2].click())
 const table=document.querySelector('[aria-label="Tích lũy và hoàn trả nhân viên"]')
 assert.ok(table)
 assert.equal(document.querySelectorAll('.payroll-personal-tracking table').length,1)
 assert.equal(table.querySelectorAll('tbody > tr').length,1)
 assert.equal([...document.querySelectorAll('.payroll-accumulation-filters button')].find(button=>button.textContent==='Đang đóng').getAttribute('aria-pressed'),'true')
 await act(async()=>[...document.querySelectorAll('.payroll-accumulation-filters button')].find(button=>button.textContent==='Xóa lọc').click())
 assert.equal(table.querySelectorAll('tbody > tr').length,3)
 assert.ok(table.textContent.includes('Đã hoàn thành đóng'))
 assert.ok(table.textContent.includes('Đang còn đóng'))
 assert.ok(table.textContent.includes('Đã nghỉ việc'))
 assert.ok(table.textContent.includes('500.000đ'))
 assert.ok(table.textContent.includes('16-09-2026'))
 assert.ok(table.querySelector('tfoot').textContent.includes('1.200.000đ'))
 assert.ok(document.querySelector('.payroll-refund-form'))
 const completed=[...table.querySelectorAll('tbody > tr')].find(row=>row.textContent.startsWith('B'))
 assert.equal(completed.querySelectorAll('button').length,0)
 const filterButton=label=>[...document.querySelectorAll('.payroll-accumulation-filters button')].find(button=>button.textContent===label)
 await act(async()=>filterButton('Hoàn thành').click())
 assert.equal(table.querySelectorAll('tbody > tr').length,1)
 assert.ok(table.querySelector('tbody').textContent.startsWith('B'))
 await act(async()=>filterButton('Đang đóng').click())
 assert.ok(table.querySelector('tbody').textContent.startsWith('A'))
 await act(async()=>filterButton('Đã hoàn trả').click())
 assert.equal(table.querySelectorAll('tbody > tr').length,1)
 assert.ok(table.querySelector('thead').textContent.includes('Đã hoàn trả'))
 assert.ok(table.querySelector('tbody').textContent.includes('100.000đ'))
 await act(async()=>filterButton('Xóa lọc').click())
 assert.equal(table.querySelectorAll('tbody > tr').length,3)
 await act(async()=>tabs[0].click())
 assert.equal(document.querySelector('[aria-label="Tích lũy và hoàn trả nhân viên"]'),null)
})
test('refunds are grouped per employee without changing paid balances or sources',()=>{
 const employees=[{employee_name:'A',role:'nhanvien',paid_total:300000,remaining:700000}]
 const refunds=[{id:'1',employee_name:'A',amount:100000},{id:'2',employee_name:'A',amount:200000},{id:'3',employee_name:'C',amount:50000}]
 const before=JSON.stringify({employees,refunds})
 const rows=accumulationRows(employees,[{employee_name:'C',employment_status:'Đã nghỉ việc'}],refunds)
 assert.equal(rows.length,2);assert.equal(rows[0].paid_total,300000);assert.equal(rows[0].configuredRefund,300000)
 assert.equal(rows[1].hasTracking,false);assert.equal(rows[1].configuredRefund,50000)
 assert.equal(JSON.stringify({employees,refunds}),before)
})

test('accumulation filters intersect employee, employment status and payment group without changing balances',()=>{
 const rows=[
  {employee_name:'A',employment_status:'Đang làm việc',hasTracking:true,remaining:100,paid_total:50,periods:[]},
  {employee_name:'B',employment_status:'Đã nghỉ việc',hasTracking:true,completed:true,remaining:0,periods:[{refund:200}]},
  {employee_name:'C',employment_status:'Đã nghỉ việc',hasTracking:false,configuredRefund:200,periods:[]},
 ]
 const before=JSON.stringify(rows)
 assert.deepEqual(filterAccumulationRows(rows,{group:'active'}).map(r=>r.employee_name),['A'])
 assert.deepEqual(filterAccumulationRows(rows,{group:'completed'}).map(r=>r.employee_name),['B'])
 assert.deepEqual(filterAccumulationRows(rows,{group:'refunded'}).map(r=>r.employee_name),['B'])
 assert.equal(filterAccumulationRows(rows,{employee:'A',status:'Đã nghỉ việc'}).length,0)
 assert.equal(filterAccumulationRows(rows,{employee:'C',group:'refunded'}).length,0)
 assert.deepEqual(filterAccumulationRows(rows),rows)
 assert.equal(JSON.stringify(rows),before)
})
