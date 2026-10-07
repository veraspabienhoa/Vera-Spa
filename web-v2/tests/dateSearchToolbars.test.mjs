import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({stdin:{contents:`import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Booking from './src/pages/OnlineBookingPage';import Schedule from './src/pages/WorkSchedulePage';import Attendance from './src/pages/SnapshotPage';import Changes from './src/pages/AdminChangesPage';const pages={Booking,Schedule,Attendance,Changes};window.act=act;window.root=createRoot(document.getElementById('root'));window.mount=key=>window.root.render(React.createElement(pages[key],{user:{role:'letan',username:'Gia Anh',permissions:{work_schedule_letan:true}}}));`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},define:{'import.meta.env':JSON.stringify({VITE_VERA_API_BASE_URL:'https://api.test'})},plugins:[{name:'fixtures',setup(b){
 b.onResolve({filter:/\/lib\/(api|supabase)$/},args=>({path:args.path.endsWith('supabase')?'auth':'api',namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},args=>({contents:args.path==='auth'?'export const getCurrentSession=async()=>({access_token:"test"});':'export const veraApi={onlineBookings:async params=>{window.bookingCalls.push(params);return {rows:[],total:0}}};'}))
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
