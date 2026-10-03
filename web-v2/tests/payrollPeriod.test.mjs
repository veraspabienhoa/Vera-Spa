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

test('empty current period stays selected until the saved draft is explicitly restored',async t=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true}),requests=[],NativeDate=Date; let savedDraft=true
 const oldDraft={period_label:'Kỳ 1 - Tháng 8/2026',rows:[{'Tên Hệ thống':'Mỹ Duyên','Tiền Lương':1000,'Số tiền thực nhận':1000}],start:'2026-08-01',end:'2026-08-15',saved_at:'2026-09-30T10:00:00Z',saved_by:'admin'}
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,
  Date:class extends NativeDate{constructor(...args){super(...(args.length?args:['2026-09-30T09:00:00Z']))}},
  fetch:async (url,options={})=>{
   const u=new URL(url);requests.push(u)
   const old=u.searchParams.get('month')==='2026-08'&&u.searchParams.get('period_no')==='1',fallback=u.searchParams.get('latest_if_missing')==='true'
   let body={}
   if(u.pathname.endsWith('/calculate-from-tips')){body=oldDraft}
   else if(u.pathname.endsWith('/draft/restore')){body={draft:savedDraft?oldDraft:null,has_saved_draft:savedDraft,selected_month:'2026-08',selected_period_no:1}}
   else if(u.pathname.endsWith('/draft')&&options.method==='PUT'){savedDraft=true;body={draft:oldDraft,message:'Đã lưu'}}
   else if(u.pathname.endsWith('/draft'))body={draft:savedDraft&&(old||fallback)?oldDraft:null,fallback_used:fallback,selected_month:'2026-08',selected_period_no:1}
   else if(u.pathname.endsWith('/history'))body={records:[],batches:[],employees:[]}
   return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
  }}
 const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 let root
 t.after(async()=>{if(root)await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}})
 const built=await build({stdin:{contents:`export {default} from './src/pages/PayrollPageEnhanced'`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"});export const isSupabaseConfigured=false;export const refreshCurrentSession=getCurrentSession;export const supabase=null'}))}}]})
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const {createRoot}=await import('react-dom/client');root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(mod.exports.default,{user:{permissions:{payroll_calculate:true,payroll_save:true,payroll_email:true,payroll_export:true}}})))
 const month=document.querySelector('input[type="month"]'),period=document.querySelector('.payroll-page-enhanced select')
 assert.equal(month.value,'2026-09');assert.equal(period.value,'2')
 assert.match(document.body.textContent,/Chưa có dữ liệu nháp cho kỳ đang chọn/)
 assert.ok(requests.some(u=>u.pathname.endsWith('/draft')))
 assert.ok(requests.some(u=>u.searchParams.get('latest_if_missing')==='true'))
 assert.deepEqual([...document.querySelectorAll('.payroll-draft-toolbar button')].map(b=>b.textContent.trim()),['Lưu bảng lương','Lấy lại bảng lương','Tính lại lương','Xóa bảng lương'])
 const restore=[...document.querySelectorAll('.payroll-draft-toolbar button')].find(button=>button.textContent.includes('Lấy lại bảng lương'))
 assert.ok(restore)
 assert.ok(restore.classList.contains('primary-button'))
 assert.equal(restore.disabled,false)
 await act(async()=>restore.click())
 assert.equal(month.value,'2026-08');assert.equal(period.value,'1')
 assert.match(document.querySelector('.payroll-draft-toolbar').textContent,/Đã lưu bởi admin/)
 assert.equal(savedDraft,true)
 assert.equal(restore.disabled,false)
 assert.equal(restore.classList.contains('primary-button'),true)
 assert.match(document.querySelector('.payroll-draft-panel').textContent,/Mỹ Duyên/)
 assert.match(document.body.textContent,/Đã lấy lại bảng lương Kỳ 1 - Tháng 8\/2026/)
 assert.ok(requests.some(u=>u.pathname.endsWith('/draft/restore')))
 const actions=[...document.querySelectorAll('.payroll-draft-panel .panel-title-row button')]
 const emailIndex=actions.findIndex(b=>b.textContent.includes('Gửi email'))
 assert.equal(actions[emailIndex+1].textContent.trim(),'Xuất excel')
 await act(async()=>document.querySelector('[data-ui-key="u-ce81fd2f3ea0"]').click())
 assert.equal(savedDraft,true)
 assert.equal(restore.disabled,false)
 assert.ok(restore.classList.contains('primary-button'))
 savedDraft=false
 const putsBefore=requests.filter(u=>u.pathname.endsWith('/draft')).length
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent.includes('Tính lương từ TIP')).click())
 assert.equal(savedDraft,true)
 assert.ok(requests.filter(u=>u.pathname.endsWith('/draft')).length>putsBefore)
})
