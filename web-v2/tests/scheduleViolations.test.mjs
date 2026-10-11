import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM as BaseJSDOM } from 'jsdom'
import { answerDialogs } from './dialogAnswers.mjs'
class JSDOM extends BaseJSDOM { constructor(...args) { super(...args); answerDialogs(this.window) } }
const boot = new JSDOM('<body/>'); globalThis.window=boot.window; globalThis.document=boot.window.document
const built = await build({entryPoints:['src/components/ScheduleViolations.jsx'],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime']})
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
after(()=>boot.window.close())
test('violation filters, manager modal and retry-safe request', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true});globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true};dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'));t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let saved=0, fail=true;const calls=[],exports=[]
 const request=async(path,options)=>{calls.push({path,options});if(options){if(fail){fail=false;throw Error('Network failed')}return {message:'Đã lưu'}}return {hc_late_approval_version:1,rows:[{id:'one',updated_at:'2026-10-06T03:00:00Z',is_manual:true,employee_name:'Yên Linh',employee_username:'linh',violation_date:'2026-10-06',reason:'Đồng phục',amount:50000},{id:'two',employee_name:'Mạnh Đạt',employee_username:'dat',violation_date:'2026-10-05',reason:'Khác',amount:10000}]}}
 const render=canEdit=>act(async()=>root.render(React.createElement(mod.exports.default,{department:'letan',employees:[{username:'linh',full_name:'Yên Linh'}],canEdit,canManage:canEdit,request,onSaved:()=>saved++,onExport:async data=>exports.push(data)})))
 const click=label=>act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent===label).click())
 await render(false);assert.ok(![...document.querySelectorAll('button')].some(b=>b.textContent.includes('Nhập phạt')))
 await render(true);await click('Tháng trước');assert.match(calls.at(-1).path,/start=\d{4}-\d{2}-01&end=/)
 await click('Tùy chỉnh');assert.ok(document.body.textContent.includes('Từ ngày'))
 await click('+ Nhập phạt vi phạm');assert.equal(document.querySelector('dialog').open,true)
 const form=document.querySelector('dialog form'),select=form.querySelector('select')
 await act(()=>{select.value='linh';select.dispatchEvent(new window.Event('change',{bubbles:true}))})
 await act(async()=>{form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await Promise.resolve()})
 assert.equal(document.querySelector('dialog').open,true);assert.match(form.textContent,/Network failed/)
 await act(async()=>{form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await Promise.resolve()})
 const posts=calls.filter(c=>c.options);assert.equal(JSON.parse(posts[0].options.body).request_id,JSON.parse(posts[1].options.body).request_id)
 assert.equal(saved,1);assert.equal(document.querySelector('dialog').open,false)
 await click('Sửa');assert.equal(document.querySelector('dialog').open,true)
 const editForm=document.querySelector('dialog form')
 await act(async()=>{editForm.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));await Promise.resolve()})
 const update=calls.find(c=>c.options?.method==='PUT');assert.ok(update.path.endsWith('/one'));assert.equal(JSON.parse(update.options.body).expected_updated_at,'2026-10-06T03:00:00Z')
 window.confirm=()=>true;await click('Xóa')
 const removal=calls.find(c=>c.options?.method==='DELETE');assert.ok(removal.path.endsWith('/one'));assert.equal(saved,3)
 await act(async()=>{
  for(const [input,value] of [[document.querySelector('input[type="search"]'),'Yên Linh'],[document.querySelector('input[aria-label="Lọc ngày vi phạm"]'),'06-10-2026']]){
   Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,value)
   input.dispatchEvent(new window.Event('input',{bubbles:true}))
  }
 })
 await click('Xuất excel')
 assert.equal(exports.length,1);assert.deepEqual(exports[0].range,{start:'2026-10-06',end:'2026-10-06'})
 assert.deepEqual(exports[0].rows.map(row=>row.id),['one'])
})

test('personal ledger uses only server-owned identity and retains month/date filters', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true});globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'));t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const calls=[];const request=async path=>{calls.push(path);return {hc_late_approval_version:1,rows:[{id:'self',employee_name:'Yên Linh',employee_username:'linh',violation_date:'2026-10-06',reason:'Đồng phục',amount:50000}]}}
 await act(async()=>root.render(React.createElement(mod.exports.default,{personal:true,request})))
 assert.match(document.body.textContent,/LỊCH SỬ VI PHẠM CỦA TÔI/)
 assert.match(document.body.textContent,/Đồng phục/)
 assert.ok(calls.every(path=>path.startsWith('/v2/work-schedule/violations/me?start=')))
 assert.ok(calls.every(path=>!path.includes('employee')&&!path.includes('department')))
 assert.equal(document.querySelector('input[type="search"]'),null)
 assert.equal(document.querySelector('dialog').textContent,'')
 assert.ok(![...document.querySelectorAll('button')].some(b=>/Nhập phạt|Sửa|Xóa/.test(b.textContent)))
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Tháng trước').click())
 assert.equal(calls.length,2)
 await act(async()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Tùy chỉnh').click())
 assert.match(document.body.textContent,/Từ ngày/)
 assert.ok(document.querySelector('input[aria-label="Lọc ngày vi phạm"]'))
})

test('HC late approval is scoped, confirmed, revision checked and preserves state after failure', async t => {
 const dom = new JSDOM('<div id="root"/>', {pretendToBeVisual:true})
 globalThis.window=dom.window; globalThis.document=dom.window.document; globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const {createRoot}=await import('react-dom/client'), root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let approved=false, fail=false, saved=0, accept=true
 window.confirm=()=>accept
 const writes=[]
 const request=async(path, options)=>{
  if(options){
   writes.push({path,body:JSON.parse(options.body)})
   if(fail) throw Error('Vi phạm vừa được thay đổi. Hãy làm mới.')
   approved=JSON.parse(options.body).approved
   return {message:'Đã cập nhật; tính lại bảng lương nháp.'}
  }
  return {hc_late_approval_version:1,rows:[
   {id:'hc',updated_at:'2026-10-06T03:00:00Z',employee_name:'Lan',employee_username:'lan',violation_date:'2026-10-06',reason:'Đi trễ · Nội quy HC',amount:approved?7500:15000,note:'Bằng chứng gốc',hc_late_approval_eligible:true,hc_late_approved:approved,hc_late_minutes:15,hc_late_approved_amount:7500,hc_late_unapproved_amount:15000},
   {id:'absence',employee_name:'Other',employee_username:'other',violation_date:'2026-10-06',reason:'Nghỉ không phép',amount:300000},
   {id:'custom',employee_name:'Custom',employee_username:'custom',violation_date:'2026-10-06',reason:'Đi trễ',amount:20000,hc_late_approval_eligible:false,hc_late_approval_unavailable:'Mức phạt tùy chỉnh'},
  ]}
 }
 const render=canManage=>act(async()=>root.render(React.createElement(React.StrictMode,null,React.createElement(mod.exports.default,{department:'support',canManage,request,onSaved:()=>saved++}))))
 await render(false)
 let check=document.querySelector('input[aria-label^="Đi trễ có phép Lan"]')
 assert.equal(check.disabled,true);assert.equal(document.querySelectorAll('input[type="checkbox"]').length,2)
 assert.match(document.body.textContent,/15 phút trễ/)
 await render(true)
 accept=false
 await act(async()=>document.querySelector('input[aria-label^="Đi trễ có phép Lan"]').click())
 assert.equal(writes.length,0);assert.equal(check.checked,false)
 accept=true
 await act(async()=>document.querySelector('input[aria-label^="Đi trễ có phép Lan"]').click())
 assert.deepEqual(writes[0],{path:'/v2/work-schedule/violations/hc/late-approval',body:{department:'support',approved:true,expected_updated_at:'2026-10-06T03:00:00Z'}})
 assert.equal(saved,1);assert.equal(document.querySelector('input[aria-label^="Đi trễ có phép Lan"]').checked,true)
 fail=true
 await act(async()=>document.querySelector('input[aria-label^="Đi trễ có phép Lan"]').click())
 assert.equal(saved,1);assert.equal(document.querySelector('input[aria-label^="Đi trễ có phép Lan"]').checked,true)
 assert.match(document.body.textContent,/vừa được thay đổi/)
 assert.match(document.body.textContent,/Bằng chứng gốc/)
 assert.equal(document.querySelector('input[aria-label^="Đi trễ có phép Custom"]').disabled,true)
})

test('pending violation confirmations and editors close on capability loss or identity remount', async t => {
 const dom=new BaseJSDOM('<div id="root"/>',{pretendToBeVisual:true})
 globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 const writes=[]
 const request=async(path,options)=>{
  if(options){writes.push({path,options});return {message:'Saved'}}
  return {hc_late_approval_version:1,rows:[{id:'hc',updated_at:'2026-10-06T03:00:00Z',employee_name:'Lan',employee_username:'lan',violation_date:'2026-10-06',reason:'HC',amount:15000,hc_late_approval_eligible:true,hc_late_approved:false,hc_late_approved_amount:7500,hc_late_unapproved_amount:15000}]}
 }
 const render=(canManage,key='account-A')=>act(async()=>root.render(React.createElement(mod.exports.default,{key,department:'support',canManage,canEdit:true,request})))
 const click=selector=>act(()=>document.querySelector(selector).click())
 await render(true)
 await click('input[type="checkbox"]')
 assert.ok(document.querySelector('[data-system-dialog="confirm"]'))
 await render(false)
 assert.equal(document.querySelector('[data-system-dialog="confirm"]'),null)
 assert.equal(writes.length,0)
 await render(true)
 await act(()=>[...document.querySelectorAll('button')].find(button=>button.textContent==='Xóa').click())
 assert.ok(document.querySelector('[data-system-dialog="confirm"]'))
 await render(false)
 assert.equal(document.querySelector('[data-system-dialog="confirm"]'),null)
 assert.equal(writes.length,0)
 await render(true)
 await act(()=>[...document.querySelectorAll('button')].find(button=>button.textContent==='Sửa').click())
 assert.equal(document.querySelector('.schedule-violation-dialog').open,true)
 await render(false)
 assert.equal(document.querySelector('.schedule-violation-dialog').open,false)
 assert.equal(document.querySelector('.schedule-violation-dialog form'),null)
 await render(true)
 await click('input[type="checkbox"]')
 assert.ok(document.querySelector('[data-system-dialog="confirm"]'))
 await render(true,'account-B')
 assert.equal(document.querySelector('[data-system-dialog="confirm"]'),null)
 assert.equal(writes.length,0)
})

test('in-flight old-account completion cannot update the replacement ledger', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true})
 globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 window.confirm=()=>true
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let finish,oldSaved=0,newSaved=0,writes=0
 const oldRequest=async(path,options)=>{
  if(options){writes++;return new Promise(resolve=>{finish=resolve})}
  return {hc_late_approval_version:1,rows:[{id:'old',updated_at:'2026-10-06T03:00:00Z',employee_name:'Old account',violation_date:'2026-10-06',amount:15000,hc_late_approval_eligible:true,hc_late_approved:false,hc_late_approved_amount:7500,hc_late_unapproved_amount:15000}]}
 }
 await act(async()=>root.render(React.createElement(mod.exports.default,{key:'A',department:'support',canManage:true,request:oldRequest,onSaved:()=>oldSaved++})))
 await act(()=>document.querySelector('input[type="checkbox"]').click())
 assert.equal(writes,1)
 await act(async()=>root.render(React.createElement(mod.exports.default,{key:'B',department:'support',canManage:true,request:async()=>({hc_late_approval_version:1,rows:[{id:'new',employee_name:'New account',violation_date:'2026-10-06',amount:10}]}),onSaved:()=>newSaved++})))
 await act(async()=>finish({message:'Old success must not appear'}))
 assert.equal(oldSaved,0);assert.equal(newSaved,0)
 assert.match(document.body.textContent,/New account/)
 assert.ok(!document.body.textContent.includes('Old account'))
 assert.ok(!document.body.textContent.includes('Old success'))
})

test('checking and unchecking automatically refresh row money, ledger total and parent statistics with fresh CAS', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true})
 globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 window.confirm=()=>true
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let approved=false,version=0,pending
 const writes=[],parentTotals=[]
 const timestamp=()=>`2026-10-06T03:00:0${version}Z`
 const amount=()=>approved?7500:15000
 const request=async(path,options)=>{
  if(options){
   const body=JSON.parse(options.body);writes.push(body)
   assert.equal(body.expected_updated_at,timestamp())
   return new Promise((resolve,reject)=>{pending={body,resolve,reject}})
  }
  return {hc_late_approval_version:1,rows:[
   {id:'hc',updated_at:timestamp(),employee_name:'Lan',employee_username:'lan',violation_date:'2026-10-06',reason:'Đi trễ · Nội quy HC',amount:amount(),hc_late_approval_eligible:true,hc_late_approved:approved,hc_late_approved_amount:7500,hc_late_unapproved_amount:15000},
   {id:'uniform',employee_name:'Other',violation_date:'2026-10-06',reason:'Đồng phục',amount:5000},
  ]}
 }
 await act(async()=>root.render(React.createElement(mod.exports.default,{department:'support',canManage:true,request,onSaved:()=>parentTotals.push(amount()+5000)})))
 const checkbox=()=>document.querySelector('input[type="checkbox"]')
 const summary=()=>document.querySelector('.schedule-violations > p:not([role]) strong').textContent
 const rowMoney=()=>document.querySelector('.schedule-scroll tbody tr').children[4].textContent
 assert.deepEqual([...document.querySelectorAll('thead th')].slice(2,5).map(th=>th.textContent),['Nội dung vi phạm','Có phép','Mức ghi nhận'])
 assert.equal(checkbox().checked,false);assert.match(rowMoney(),/^15\.000đ/);assert.equal(summary(),'20.000đ')
 for(const [next,total,text] of [[true,'12.500đ','7.500đ'],[false,'20.000đ','15.000đ']]){
  await act(()=>checkbox().click())
  assert.equal(checkbox().disabled,true);assert.equal(checkbox().checked,!next)
  assert.equal(document.querySelector('.schedule-violation-dialog form'),null)
  await act(async()=>{approved=pending.body.approved;version++;pending.resolve({amount:amount(),approved,message:'Đã tự tính lại tiền phạt.'})})
  assert.equal(checkbox().checked,next);assert.equal(checkbox().disabled,false)
  assert.ok(rowMoney().startsWith(text));assert.equal(summary(),total)
 }
 assert.deepEqual(writes.map(body=>body.approved),[true,false])
 assert.notEqual(writes[0].expected_updated_at,writes[1].expected_updated_at)
 assert.deepEqual(parentTotals,[12500,20000])
 await act(()=>checkbox().click())
 await act(async()=>pending.reject(Error('Không lưu được; số tiền chưa thay đổi.')))
 assert.equal(checkbox().checked,false);assert.match(rowMoney(),/^15\.000đ/);assert.equal(summary(),'20.000đ')
 assert.deepEqual(parentTotals,[12500,20000])
})

test('ledger export cannot download or show stale feedback after filter or capability changes', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true})
 globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let finish,options,downloads=0
 const request=async()=>({hc_late_approval_version:1,rows:[{id:'hc',employee_name:'Lan',violation_date:'2026-10-06',reason:'HC',amount:15000}]})
 const onExport=async(_data,scope)=>{options=scope;await new Promise(resolve=>{finish=resolve});scope.assertCurrent();downloads++}
 const render=canManage=>act(async()=>root.render(React.createElement(mod.exports.default,{department:'support',canManage,request,onExport})))
 const click=label=>act(async()=>{[...document.querySelectorAll('button')].find(button=>button.textContent===label).click();await Promise.resolve()})
 await render(true)
 await click('Xuất excel');await click('Tháng trước')
 assert.equal(options.signal.aborted,true)
 await act(async()=>finish())
 assert.equal(downloads,0);assert.equal(document.querySelector('[role="status"]'),null)
 await click('Xuất excel');await render(false)
 assert.equal(options.signal.aborted,true)
 await act(async()=>finish())
 assert.equal(downloads,0);assert.equal(document.querySelector('[role="status"]'),null)
})

test('mixed-version ledger gates approvals, survives a cached-capability 404 and re-enables after backend upgrade', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true})
 globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 window.confirm=()=>true
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let stage='legacy',rejectNext=false,approved=false,saved=0
 const writes=[]
 const request=async(path,options)=>{
  if(options){
   writes.push({path,body:JSON.parse(options.body)})
   if(rejectNext){rejectNext=false;stage='stale';throw Object.assign(Error('Not Found'),{status:404})}
   approved=JSON.parse(options.body).approved
   return {amount:7500,approved,message:'Đã cập nhật.'}
  }
  const row={id:'hc',updated_at:'2026-10-06T03:00:00Z',employee_name:'Lan',employee_username:'lan',violation_date:'2026-10-06',reason:'Đi trễ · Nội quy HC',amount:approved?7500:15000}
  if(stage!=='legacy') Object.assign(row,{hc_late_approval_eligible:true,hc_late_approved:approved,hc_late_approved_amount:7500,hc_late_unapproved_amount:15000})
  return {...(stage==='new'?{hc_late_approval_version:1}:{}),rows:[row]}
 }
 await act(async()=>root.render(React.createElement(mod.exports.default,{department:'support',canManage:true,canEdit:true,request,onSaved:()=>saved++})))
 const click=label=>act(async()=>{[...document.querySelectorAll('button')].find(button=>button.textContent===label).click();await Promise.resolve()})
 const moneyCell=()=>document.querySelector('.schedule-scroll tbody tr').children[4].textContent
 assert.match(document.body.textContent,/Máy chủ chưa hỗ trợ Đi trễ có phép/)
 assert.match(moneyCell(),/^15\.000đ/);assert.equal(document.querySelector('input[type="checkbox"]'),null)
 // Ordinary manual entry remains available on the old ledger contract.
 await click('+ Nhập phạt vi phạm');assert.equal(document.querySelector('.schedule-violation-dialog').open,true)
 await click('Đóng')
 stage='stale';await click('Tháng trước')
 assert.equal(document.querySelector('input[type="checkbox"]').disabled,true)
 await act(()=>document.querySelector('input[type="checkbox"]').click());assert.equal(writes.length,0)
 stage='new';await click('Tháng này')
 assert.equal(document.querySelector('input[type="checkbox"]').disabled,false)
 assert.ok(!document.body.textContent.includes('Máy chủ chưa hỗ trợ Đi trễ có phép'))
 rejectNext=true
 await act(async()=>document.querySelector('input[type="checkbox"]').click())
 assert.equal(writes.length,1);assert.equal(saved,0)
 assert.equal(document.querySelector('input[type="checkbox"]').checked,false)
 assert.equal(document.querySelector('input[type="checkbox"]').disabled,true)
 assert.match(moneyCell(),/^15\.000đ/)
 assert.match(document.body.textContent,/Máy chủ chưa hỗ trợ Đi trễ có phép/)
 stage='new';await click('Tháng trước')
 await act(async()=>document.querySelector('input[type="checkbox"]').click())
 assert.equal(writes.length,2);assert.equal(saved,1)
 assert.equal(document.querySelector('input[type="checkbox"]').checked,true)
 assert.match(moneyCell(),/^7\.500đ/)
})
