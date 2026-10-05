import test from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React,{act} from 'react'
import {JSDOM} from 'jsdom'
test('history has twelve columns, full mobile details, filtered totals and safe email/export',async t=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true}),requests=[],NativeDate=Date
 const records=[{ 'Tên Hệ thống':'An Nhiên','Họ và tên':'Tên A',Email:'a@example.test','Mã bản lưu':'Kỳ 2 tháng 9','Từ ngày':'2026-09-16','Đến ngày':'2026-09-30','Tiền Lương':1000,'Tiền Hỗ Trợ Hoàn Lại':200,'Hoàn trả tiền tích lũy':300,'Tích lũy':400,'Chi Phí Sinh Hoạt':500,'Tiền phạt trong tháng':600,'Vi phạm kỳ trước':700,'Tiền ứng lương':800,'Tiền hỗ trợ Locker':900,'Số tiền thực nhận':-1500,__employment_status:'Đã nghỉ việc'},{'Tên Hệ thống':'B','Tiền Lương':2000,'Số tiền thực nhận':1000,__employment_status:'Đang làm việc'},{'Tên Hệ thống':'C','Tiền Lương':3000,'Số tiền thực nhận':-500,__employment_status:'Đang làm việc'}]
 const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,
  Date:class extends NativeDate{constructor(...args){super(...(args.length?args:['2026-09-30T09:00:00Z']))}},
  fetch:async (url,options={})=>{
   const u=new URL(url);requests.push({url:u,options})
   const body=u.pathname.endsWith('/history')?{records,batches:[],employees:[]}:u.pathname.endsWith('/email')?{sent:['a'],failed:[]}:{}
   return new Response(JSON.stringify(body),{status:200,headers:{'Content-Type':'application/json'}})
  }}
 const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 let root
 t.after(async()=>{if(root)await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}})
 const built=await build({stdin:{contents:`export {default} from './src/pages/PayrollPageEnhanced'`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"});export const isSupabaseConfigured=false;export const refreshCurrentSession=getCurrentSession;export const supabase=null'}))}}]})
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const {createRoot}=await import('react-dom/client');root=createRoot(document.getElementById('root'))
 await act(async()=>root.render(React.createElement(mod.exports.default,{user:{role:'admin'},activeTab:'history'})))

 assert.equal(document.querySelector('#ktv-payroll-history-content').hidden,true)
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Hiện lịch sử').click())
 assert.equal(document.querySelector('#ktv-payroll-history-content').hidden,false)
 const panel=document.querySelector('.payroll-history-panel'),table=panel.querySelector('table')
 assert.equal(table.querySelectorAll('thead th').length,12)
 assert.equal(table.querySelectorAll('tbody tr').length,3)
 const expected=['Gửi','Nhân viên','Lương','Trách nhiệm-hỗ trợ','Hoàn trả tích lũy','Tích lũy','Phí sinh hoạt','Vi phạm kỳ này','Nợ vi phạm kỳ trước','Tiền ứng','Hỗ trợ Locker','Thực nhận']
 assert.deepEqual([...table.querySelectorAll('thead th')].map(th=>th.textContent),expected)
 assert.ok(table.textContent.includes('a@example.test'));assert.ok(table.textContent.includes('Kỳ 2 tháng 9'))
 assert.equal(panel.querySelector('.payroll-history-mobile .payroll-history-summary').children.length,10)
 const click=async label=>act(async()=>[...panel.querySelectorAll('button')].find(button=>button.textContent.trim()===label).click())
 await click('Thực nhận ≤ 0');assert.equal(table.querySelectorAll('tbody tr').length,2)
 await click('Đã nghỉ việc');assert.equal(table.querySelectorAll('tbody tr').length,1)
 assert.ok(panel.querySelector('.payroll-column-summary').textContent.includes('1.000đ'))
 assert.ok(panel.querySelector('.payroll-column-summary').textContent.includes('900đ'))
 assert.ok(panel.querySelector('.payroll-column-summary').textContent.includes('-1.500đ'))
 window.confirm=()=>true;window.HTMLAnchorElement.prototype.click=()=>{}
 await act(async()=>panel.querySelector('.payroll-select-all input').click())
 await click('Gửi email (1)')
 const email=requests.find(request=>request.url.pathname.endsWith('/email'))
 assert.equal(JSON.parse(email.options.body).rows.length,1)
 assert.equal(JSON.parse(email.options.body).rows[0]['Tên Hệ thống'],'An Nhiên')
 await click('Excel lịch sử')
 const exported=requests.find(request=>request.url.pathname.endsWith('/history/export.xlsx'))
 assert.equal(exported.url.searchParams.get('former_only'),'true');assert.equal(exported.url.searchParams.get('non_positive_only'),'true')
 await click('Xóa lọc');assert.equal(table.querySelectorAll('tbody tr').length,3)
 const search=panel.querySelector('input[type="search"]')
 await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(search,'an nhien');search.dispatchEvent(new window.Event('input',{bubbles:true}))})
 assert.equal(table.querySelectorAll('tbody tr').length,1)
 assert.equal(panel.querySelector('.payroll-select-all input').checked,false)
 assert.equal(JSON.parse(JSON.stringify(records))[0]['Số tiền thực nhận'],-1500)
})
