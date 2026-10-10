import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { trainingDateRange, readCompleteTrainingReport, validTrainingScore } from '../src/lib/trainingReport.js'

test('inclusive training calendar dates, leap months, custom bounds and missing scores', () => {
  assert.deepEqual(trainingDateRange({ mode:'all' }), {})
  assert.deepEqual(trainingDateRange({ mode:'day', day:'2026-10-11' }), {date_from:'2026-10-11',date_to:'2026-10-11'})
  assert.deepEqual(trainingDateRange({ mode:'month', month:'2024-02' }), {date_from:'2024-02-01',date_to:'2024-02-29'})
  assert.deepEqual(trainingDateRange({ mode:'month', month:'2026-02' }), {date_from:'2026-02-01',date_to:'2026-02-28'})
  for(const value of [{mode:'day',day:'2026-02-29'},{mode:'custom',start:'2026-10-12',end:'2026-10-11'},{mode:'month',month:'2026-13'},{mode:'custom',start:'2026-10-01',end:''}])assert.equal(trainingDateRange(value),null)
  for(const value of [null,undefined,'',0,-1,6,'bad'])assert.equal(validTrainingScore(value),false)
})
const historyRow=id=>({id:String(id),type:'daily',date:'2026-10-10',title:`Buổi ${id}`,detail:{skill_grade:'A',learning_attitude:'Tốt',notes:`Ghi chú ${id}`}})
const report=(employee='Linh Đan',count=1)=>({employee_username:employee,history_total:count,history:Array.from({length:Math.min(count,100)},(_,i)=>historyRow(i)),progress:[{id:'s1',training_date:'2026-10-10',start_time:'09:00',end_time:'10:00',skill_grade:'A',skill_score:5,notes:'Nhật ký đầy đủ'}],latest_radar:null})
test('pagination fetches all records with identical filters and abort signal, never silently truncates',async()=>{
 const calls=[],controller=new AbortController()
 const result=await readCompleteTrainingReport(async(...args)=>{calls.push(args);return args[1].page===2?{...report('Linh Đan',101),history:[historyRow(100)]}:report('Linh Đan',101)},'Linh Đan',{date_from:'2026-10-01',date_to:'2026-10-31'},controller.signal)
 assert.equal(result.history.length,101);assert.ok(calls.every(c=>c[1].date_from==='2026-10-01'&&c[1].date_to==='2026-10-31'&&c[2].signal===controller.signal))
 await assert.rejects(readCompleteTrainingReport(async()=>({...report(),history_total:2}),'x',{},controller.signal),/Dữ liệu đã thay đổi/)
 controller.abort();await assert.rejects(readCompleteTrainingReport(async()=>report(),'x',{},controller.signal),e=>e.name==='AbortError')
})
const built=await build({stdin:{contents:"export { default } from './src/pages/TrainingPage'",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react-dom/client','react/jsx-runtime'],loader:{'.css':'empty'},plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const veraApi=new Proxy({}, {get:(_,key)=>(...args)=>window.api(key,...args)})'}))}}]})
const user={id:'admin-1',username:'Admin',role:'admin',permissions:{training_view:true}}
function deferred(){let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b});return{promise,resolve,reject}}
async function fixture(overrides={}){
 const dom=new JSDOM('<button id="opener">Open</button><div id="root"></div>',{url:'https://example.test',pretendToBeVisual:true}),w=dom.window
 const values={window:w,document:w.document,navigator:w.navigator,File:w.File,URL:w.URL,IS_REACT_ACT_ENVIRONMENT:true},saved=Object.fromEntries(Object.keys(values).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const[key,value]of Object.entries(values))Object.defineProperty(globalThis,key,{value,configurable:true})
 const calls=[],urls=[],revoked=[],shares=[]
 URL.createObjectURL=file=>{const url=`blob:training-${urls.length+1}`;urls.push({url,file});return url};URL.revokeObjectURL=url=>revoked.push(url)
 navigator.canShare=()=>true;navigator.share=data=>{shares.push(data);return overrides.share?overrides.share(data):Promise.resolve()}
 w.api=(method,...args)=>{calls.push({method,args});if(overrides[method])return overrides[method](...args)
  if(method==='trainingBootstrap')return Promise.resolve({people:[],assignments:[],notification_recipients:[],notifications:[],training_students:[]})
  if(method==='trainingReportEmployees')return Promise.resolve({employees:[{username:'Linh Đan',full_name:'Linh Đan',role:'nhanvien'},{username:'Minh An',full_name:'Minh An',role:'nhanvien'}]})
  if(method==='trainingReport')return Promise.resolve(report(args[0]))
  if(method==='readTrainingReportExport')return Promise.resolve(new w.Blob([args[1]],{type:args[1]==='pdf'?'application/pdf':'image/png'}))
  throw Error(`Unexpected ${method}`)
 }
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const{createRoot}=await import('react-dom/client'),root=createRoot(document.querySelector('#root'));let mounted=true
 const render=next=>act(async()=>root.render(React.createElement(mod.exports.default,{user:next})));await render(user)
 const button=text=>[...document.querySelectorAll('button')].find(b=>b.textContent===text)
 const click=node=>act(async()=>node.click())
 const type=(node,value)=>act(async()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new w.Event('input',{bubbles:true}))})
 const select=value=>act(async()=>{const node=document.querySelector('select[aria-label="Thời gian đào tạo"]');node.value=value;node.dispatchEvent(new w.Event('change',{bubbles:true}))})
 const unmount=async()=>{if(mounted){await act(async()=>root.unmount());mounted=false}}
 return{w,calls,urls,revoked,shares,render,button,click,type,select,unmount,open:()=>click(button('Báo cáo tiến độ')),dispose:async()=>{try{await unmount()}finally{w.close();for(const[key,descriptor]of Object.entries(saved)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key]}}}}
}
test('filters below heading, searchable names and complete employee modal preserve history and exports',async()=>{
 const f=await fixture({trainingReport:async(employee,filters)=>filters.page===2?{...report(employee,101),history:[historyRow(100)]}:report(employee,101)})
 try{
  assert.equal(f.button('Lịch sử'),undefined);await f.open()
  assert.equal(document.querySelector('.training-employee-roster h2').nextElementSibling.className,'training-progress-filters');assert.equal(document.querySelector('.compact-filter'),null)
  await f.type(document.querySelector('[role=combobox]'),'linh dan');assert.equal(document.querySelectorAll('.training-employee-roster tbody tr').length,1)
  await f.click(f.button('Linh Đan'));assert.ok(document.querySelector('[role=dialog]'))
  for(const label of ['Nhật ký đào tạo','Năng lực kỳ gần nhất','Tiến độ kỹ năng','Biểu đồ đánh giá','Buổi 100','Chưa có đủ dữ liệu năng lực'])assert.ok(document.body.textContent.includes(label),label)
  assert.equal(f.calls.filter(c=>c.method==='readTrainingReportExport').length,0)
  await f.click(f.button('Xem / tải / chia sẻ PNG và PDF'));assert.equal(f.calls.filter(c=>c.method==='readTrainingReportExport').length,2)
  for(const label of ['Xem PDF','Xem PNG','Tải PDF','Tải PNG'])assert.ok([...document.querySelectorAll('a')].some(a=>a.textContent===label))
  await f.click(f.button('Chia sẻ PNG'));assert.equal(f.shares[0].files[0].type,'image/png')
  await f.click(document.querySelector('[aria-label="Đóng báo cáo đào tạo"]'));assert.equal(document.querySelector('[role=dialog]'),null);assert.deepEqual(f.revoked,f.urls.map(x=>x.url))
 }finally{await f.dispose()}
})
test('day/month/custom filters update roster; incomplete date hides old data without loading old date',async()=>{
 const f=await fixture()
 try{
  await f.open();await f.select('day');await f.type(document.querySelector('input[aria-label="Ngày đào tạo"]'),'10-10-2026')
  assert.deepEqual(f.calls.filter(c=>c.method==='trainingReportEmployees').at(-1).args[0],{date_from:'2026-10-10',date_to:'2026-10-10'})
  const count=f.calls.length;await f.type(document.querySelector('input[aria-label="Ngày đào tạo"]'),'12');assert.equal(document.querySelector('.training-employee-roster table'),null);assert.equal(f.calls.length,count)
  await f.select('month');await f.type(document.querySelector('input[type=month]'),'2024-02');assert.deepEqual(f.calls.filter(c=>c.method==='trainingReportEmployees').at(-1).args[0],{date_from:'2024-02-01',date_to:'2024-02-29'})
  await f.select('custom');await f.type(document.querySelector('input[aria-label="Đào tạo từ ngày"]'),'01-09-2026');await f.type(document.querySelector('input[aria-label="Đào tạo đến ngày"]'),'30-09-2026')
  assert.deepEqual(f.calls.filter(c=>c.method==='trainingReportEmployees').at(-1).args[0],{date_from:'2026-09-01',date_to:'2026-09-30'})
  await f.click(f.button('Linh Đan'));assert.deepEqual(f.calls.findLast(c=>c.method==='trainingReport').args[1],{date_from:'2026-09-01',date_to:'2026-09-30',page_size:100})
 }finally{await f.dispose()}
})
test('account switch and permission revocation hide data and invalidate late report/export state',async()=>{
 const late=deferred(),f=await fixture({trainingReport:()=>late.promise})
 try{
  await f.open();await f.click(f.button('Linh Đan'));const old=f.calls.findLast(c=>c.method==='trainingReport').args[2].signal
  await f.render({...user,id:'admin-2'});assert.equal(document.querySelector('[role=dialog]'),null);assert.equal(old.aborted,true)
  await act(async()=>late.resolve(report('OLD PRIVATE EMPLOYEE')));assert.doesNotMatch(document.body.textContent,/OLD PRIVATE EMPLOYEE/)
  await f.open();await f.click(f.button('Linh Đan'));await f.click(f.button('Xem / tải / chia sẻ PNG và PDF'));assert.equal(f.urls.length,2)
  await f.render({id:'leader-1',role:'leader',permissions:{training_view:false}});assert.equal(document.querySelector('#root').textContent,'');assert.deepEqual(f.revoked,f.urls.map(x=>x.url))
 }finally{await f.dispose()}
})
test('share is a direct user gesture; duplicate click and cancellation safe; Escape restores focus',async()=>{
 const pending=deferred();let inClick=false;const f=await fixture({share:()=>{assert.equal(inClick,true);return pending.promise}})
 try{
  await f.open();f.button('Linh Đan').focus();await f.click(f.button('Linh Đan'));await f.click(f.button('Xem / tải / chia sẻ PNG và PDF'))
  await act(async()=>{inClick=true;f.button('Chia sẻ PDF').click();f.button('Chia sẻ PDF').click();inClick=false});assert.equal(f.shares.length,1);assert.equal(document.querySelector('[aria-label="Đóng báo cáo đào tạo"]').disabled,true)
  await act(async()=>pending.reject(Object.assign(Error('cancel'),{name:'AbortError'})));assert.equal(document.querySelector('[role=alert]'),null)
  await act(async()=>document.querySelector('[role=dialog]').dispatchEvent(new f.w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})));assert.equal(document.querySelector('[role=dialog]'),null);assert.equal(document.activeElement.textContent,'Linh Đan')
 }finally{await f.dispose()}
})
test('closing generation aborts both exports; late files never create object URLs',async()=>{
 const pending=deferred(),f=await fixture({readTrainingReportExport:()=>pending.promise})
 try{
  await f.open();await f.click(f.button('Linh Đan'));await f.click(f.button('Xem / tải / chia sẻ PNG và PDF'))
  const signals=f.calls.filter(c=>c.method==='readTrainingReportExport').map(c=>c.args[3].signal)
  await f.click(document.querySelector('[aria-label="Đóng báo cáo đào tạo"]'));assert.ok(signals.every(s=>s.aborted))
  await act(async()=>pending.resolve(new f.w.Blob(['private'])));assert.deepEqual(f.urls,[])
 }finally{await f.dispose()}
})

test('late roster from obsolete dates is aborted and never replaces current authorized options',async()=>{
 const pending=deferred(),f=await fixture({trainingReportEmployees:filters=>filters.date_from==='2026-10-09'?pending.promise:Promise.resolve({employees:[{username:'New current',role:'nhanvien'}]})})
 try{
  await f.open();await f.select('day');await f.type(document.querySelector('input[aria-label="Ngày đào tạo"]'),'09-10-2026')
  const old=f.calls.findLast(c=>c.method==='trainingReportEmployees').args[1].signal
  await f.type(document.querySelector('input[aria-label="Ngày đào tạo"]'),'10-10-2026');assert.equal(old.aborted,true)
  await act(async()=>pending.resolve({employees:[{username:'OLD PRIVATE ROSTER',role:'nhanvien'}]}))
  assert.ok(f.button('New current'));assert.doesNotMatch(document.body.textContent,/OLD PRIVATE ROSTER/)
 }finally{await f.dispose()}
})

test('server export denial closes selected report and removes every prepared file',async()=>{
 let denied=false
 const f=await fixture({trainingReportEmployees:()=>denied?Promise.reject(Object.assign(Error('Quyền đã bị thu hồi'),{status:403})):Promise.resolve({employees:[{username:'Linh Đan',role:'nhanvien'}]}),readTrainingReportExport:(_employee,format)=>{if(format==='png'){denied=true;return Promise.reject(Object.assign(Error('Quyền đã bị thu hồi'),{status:403}))}return Promise.resolve(new Blob(['pdf'],{type:'application/pdf'}))}})
 try{
  await f.open();await f.click(f.button('Linh Đan'));await f.click(f.button('Xem / tải / chia sẻ PNG và PDF'))
  assert.equal(document.querySelector('[role=dialog]'),null);assert.equal(document.querySelector('a[download]'),null);assert.match(document.body.textContent,/Quyền đã bị thu hồi/)
  assert.deepEqual(f.revoked,f.urls.map(x=>x.url))
 }finally{await f.dispose()}
})


test('same-count edits between history pages fail closed instead of mixing chart snapshots',async()=>{
 const initial=report('Linh Đan',101),changed={...initial,progress:initial.progress.map(item=>({...item,skill_score:1})),history:[historyRow(100)]}
 const controller=new AbortController()
 await assert.rejects(readCompleteTrainingReport(async(_employee,filters)=>filters.page===2?changed:initial,'Linh Đan',{},controller.signal),/Dữ liệu đã thay đổi/)
})
