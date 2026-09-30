import test from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React,{act} from 'react'
import {JSDOM} from 'jsdom'
import {currentPayrollPeriod} from '../src/lib/payrollPeriod.js'

test('Vietnam payroll defaults: September 30, half-month, month and year boundaries',()=>{
 for(const [timestamp,month,periodNo] of [
  ['2026-09-30T09:00:00Z','2026-09',2],
  ['2026-09-15T16:59:59Z','2026-09',1],
  ['2026-09-15T17:00:00Z','2026-09',2],
  ['2026-09-30T17:00:00Z','2026-10',1],
  ['2026-12-31T17:00:00Z','2027-01',1],
 ]) assert.deepEqual(currentPayrollPeriod(new Date(timestamp)),{month,periodNo})
})

test('empty current period stays selected; older draft requires explicit selection',async t=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true}),requests=[],NativeDate=Date
 const oldDraft={period_label:'Kỳ 1 - Tháng 8/2026',rows:[],start:'2026-08-01',end:'2026-08-15'}
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,
  Date:class extends NativeDate{constructor(...args){super(...(args.length?args:['2026-09-30T09:00:00Z']))}},
  fetch:async url=>{
   const u=new URL(url);requests.push(u)
   const old=u.searchParams.get('month')==='2026-08'&&u.searchParams.get('period_no')==='1',fallback=u.searchParams.get('latest_if_missing')==='true'
   const body=u.pathname.endsWith('/draft')?{draft:old||fallback?oldDraft:null,fallback_used:fallback,selected_month:'2026-08',selected_period_no:1}:u.pathname.endsWith('/history')?{records:[],batches:[],employees:[]}:{}
   return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
  }}
 const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 let root
 t.after(async()=>{if(root)await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}})
 const built=await build({stdin:{contents:`export {default} from './src/pages/PayrollPageEnhanced'`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"});export const isSupabaseConfigured=false;export const refreshCurrentSession=getCurrentSession;export const supabase=null'}))}}]})
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const {createRoot}=await import('react-dom/client');root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(mod.exports.default,{user:{permissions:{payroll_calculate:true}}})))
 const month=document.querySelector('input[type="month"]'),period=document.querySelector('.payroll-page-enhanced select')
 assert.equal(month.value,'2026-09');assert.equal(period.value,'2')
 assert.match(document.body.textContent,/Chưa có dữ liệu nháp cho kỳ đang chọn/)
 assert.ok(requests.some(u=>u.pathname.endsWith('/draft')))
 assert.ok(requests.every(u=>!u.searchParams.has('latest_if_missing')))
 const change=async(node,value)=>act(async()=>{Object.getOwnPropertyDescriptor(node.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event(node.tagName==='SELECT'?'change':'input',{bubbles:true}))})
 await change(month,'2026-08');await change(period,'1')
 assert.equal(month.value,'2026-08');assert.equal(period.value,'1')
 assert.ok(requests.some(u=>u.searchParams.get('month')==='2026-08'&&u.searchParams.get('period_no')==='1'))
})
