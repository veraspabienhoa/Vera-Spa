import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { monthlyStatisticsExportRows, violationExportRows } from '../src/lib/scheduleTableRows.js'

test('schedule Excel snapshot keeps hidden penalties masked and numeric totals intact',()=>{
 const item={workDays:2,offDays:1,ca1Days:1,ca2Days:1,overtimeHours:1.234,violations:2,penalty:50000}
 const data={rows:[{...item,username:'mine',name:'Tên tôi'},{...item,username:'other',name:'Tên khác'}],departmentTotal:item}
 const result=monthlyStatisticsExportRows(data,'Locker',username=>username==='mine',false)
 assert.deepEqual(result[0].slice(5),[1.23,2,50000])
 assert.deepEqual(result[1].slice(6),['—','—'])
 assert.deepEqual(result[2].slice(6),['—','—'])
 assert.ok(monthlyStatisticsExportRows(data,'Locker',()=>true,true,true).every(row=>row[6]==='—'&&row[7]==='—'))
 const violation=violationExportRows([{employee_name:'Tên tôi',violation_date:'2026-10-07',reason:'Lỗi',amount:50000,note:'Ghi chú',created_at:'2026-10-07T12:00:00Z'}])
 assert.equal(violation[0][1],'07-10-2026');assert.equal(violation[0][6],'07-10-2026 19:00:00')
 assert.equal(violation[0][3],50000);assert.equal(violation.at(-1)[3],50000)
})
const built = await build({stdin:{contents:`import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Booking from './src/pages/OnlineBookingPage';import Schedule from './src/pages/WorkSchedulePage';import Attendance from './src/pages/SnapshotPage';import Changes from './src/pages/AdminChangesPage';const pages={Booking,Schedule,Attendance,Changes};window.act=act;window.root=createRoot(document.getElementById('root'));window.mount=(key,role='letan')=>window.root.render(React.createElement(pages[key],{user:{role,username:'Gia Anh',permissions:{work_schedule_letan:true}}}));`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env':JSON.stringify({VITE_VERA_API_BASE_URL:'https://api.test'})},plugins:[{name:'fixtures',setup(b){
 b.onResolve({filter:/\/lib\/(api|supabase)$/},args=>({path:args.path.endsWith('supabase')?'auth':'api',namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},args=>({contents:args.path==='auth'?'export const getCurrentSession=async()=>({access_token:"test"});':'export const apiRequest=async(path,options={})=>(await fetch("https://api.test"+path,options)).json();export const veraApi={onlineBookings:async params=>{window.bookingCalls.push(params);return {rows:[],total:0}}};'}))
}}]})
for (const [page,label,path] of [['Booking','Ngày booking',''],['Schedule','Ngày lịch làm việc','/v2/work-schedule'],['Attendance','Ngày chấm công','/v2/snapshot'],['Changes','Ngày thay đổi hệ thống','/v2/admin/changes-v41']]) {
 test(`${page}: typed date and picker apply one day; incomplete drafts do not reload`,async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,calls=[]
  w.MessageChannel=class{constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
  w.HTMLDialogElement.prototype.close=function(){this.open=false};w.HTMLDialogElement.prototype.showModal=function(){this.open=true};
  w.Headers=Headers;w.IS_REACT_ACT_ENVIRONMENT=true;w.bookingCalls=[]
  w.fetch=async url=>{calls.push(new URL(url));return {ok:true,json:async()=>({employees:[],rows:[],records:[],changes:[],archive:[],filters:{employees:[],departments:[],shifts:[]}})}}
  w.eval(built.outputFiles[0].text)
  try {
   await w.act(async()=>w.mount(page))
   const input=w.document.querySelector(`input[aria-label="${label}"]`)
   assert.ok(input.closest('.date-search-toolbar'))
   if(['Attendance','Changes'].includes(page))assert.deepEqual([...input.closest('.date-search-toolbar').querySelectorAll(':scope>button')].map(b=>b.textContent),['Hôm nay','Hôm qua','Tuần này','Tuần trước','Tháng này','Tháng trước','Tùy chỉnh'])
   const reads=()=>path?calls.filter(c=>c.pathname===path):w.bookingCalls
   const count=reads().length
   const type=async(node,value,event='input')=>w.act(async()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new w.Event(event,{bubbles:true}))})
   await type(input,'07');assert.equal(reads().length,count)
   await type(input,'07102026');assert.equal(input.value,'07-10-2026')
   const range=()=>path?Object.fromEntries((page==='Schedule'?reads().findLast(c=>c.searchParams.get('start')===c.searchParams.get('end')):reads().at(-1)).searchParams):reads().at(-1)
   assert.equal(range()[path?'start':'date_from'],'2026-10-07');assert.equal(range()[path?'end':'date_to'],'2026-10-07')
   await type(input,'31-02-2026');assert.equal(input.getAttribute('aria-invalid'),'true');assert.equal(range()[path?'start':'date_from'],'2026-10-07')
   await type(input.closest('.vera-date-input').querySelector('input[type=date]'),'2026-10-09','change')
   assert.equal(input.value,'09-10-2026');assert.equal(range()[path?'start':'date_from'],'2026-10-09');assert.equal(range()[path?'end':'date_to'],'2026-10-09')
  } finally {await w.act(async()=>w.root.unmount());w.close()}
 })
}

test('every work-schedule department displays its own violation ledger on tab changes',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,calls=[]
 w.MessageChannel=class{constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 w.HTMLDialogElement.prototype.close=function(){this.open=false};w.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 w.Headers=Headers;w.IS_REACT_ACT_ENVIRONMENT=true
 w.fetch=async url=>{const u=new URL(url);calls.push(u);const department=u.searchParams.get('department');return {ok:true,json:async()=>({employees:[],rows:u.pathname.endsWith('/violations')?[{id:department,employee_name:department,violation_date:'2026-10-07',reason:`Violation ${department}`,amount:10000}]:[],shift_definitions:{}})}}
 w.eval(built.outputFiles[0].text)
 try{
  await w.act(async()=>w.mount('Schedule','admin'))
  for(const [department,label] of [['locker','Locker'],['letan','Lễ tân'],['tapvu','Tạp vụ'],['quanly','Quản lý'],['locker','Locker']]){
   await w.act(async()=>[...w.document.querySelectorAll('.schedule-department-tabs button')].find(b=>b.textContent===label).click())
   const ledger=w.document.querySelector('.schedule-violations')
   assert.match(ledger.querySelector('h3').textContent,new RegExp(`VI PHẠM · PHẠT VI PHẠM · ${label}`))
   assert.match(ledger.textContent,new RegExp(`Violation ${department}`))
   assert.ok(calls.some(u=>u.pathname.endsWith('/violations')&&u.searchParams.get('department')===department))
   assert.ok(ledger.compareDocumentPosition(w.document.querySelector('.monthly-statistics'))&w.Node.DOCUMENT_POSITION_PRECEDING)
   assert.ok([...ledger.querySelectorAll('button')].some(button => button.textContent === 'Xuất excel'))
   assert.ok([...w.document.querySelectorAll('.monthly-statistics button')].some(button => button.textContent === 'Xuất excel'))
  }
 }finally{await w.act(async()=>w.root.unmount());w.close()}
})

for (const [page,label,path] of [['Schedule','Ngày lịch làm việc','/v2/work-schedule'],['Changes','Ngày thay đổi hệ thống','/v2/admin/changes-v41']]) {
 test(`${page}: a slow previous date cannot overwrite the new selection`, async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window
  w.MessageChannel=class{constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
  w.HTMLDialogElement.prototype.close=function(){this.open=false};w.HTMLDialogElement.prototype.showModal=function(){this.open=true}
  w.Headers=Headers;w.IS_REACT_ACT_ENVIRONMENT=true
  let releaseOld,oldSignal
  const payload=name=>({employees:name?[{username:name,role:'letan',employment_status:'Đang làm việc'}]:[],rows:[],changes:name?[{id:name,employee_name:name,event_type:'insert',created_at:'2026-10-08T12:00:00Z'}]:[],archive:[]})
  w.fetch=async(url,options={})=>{
   const u=new URL(url),day=u.searchParams.get('start')
   if(u.pathname===path&&day===u.searchParams.get('end')&&day==='2026-10-07') {
    oldSignal=options.signal
    return new Promise(resolve=>{releaseOld=()=>resolve({ok:true,json:async()=>payload('Old response')})})
   }
   return {ok:true,json:async()=>payload(u.pathname===path&&day==='2026-10-08'?'New response':'')}
  }
  w.eval(built.outputFiles[0].text)
  try {
   await w.act(async()=>w.mount(page))
   const input=w.document.querySelector(`input[aria-label="${label}"]`)
   const type=value=>w.act(async()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new w.Event('input',{bubbles:true}))})
   await type('07-10-2026');assert.ok(releaseOld)
   await type('08-10-2026');assert.equal(oldSignal.aborted,true)
   assert.match(w.document.body.textContent,/New response/)
   await w.act(async()=>releaseOld())
   assert.match(w.document.body.textContent,/New response/)
   assert.doesNotMatch(w.document.body.textContent,/Old response/)
  } finally {await w.act(async()=>w.root.unmount());w.close()}
 })
}
