import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const boot = new JSDOM('<body/>'); globalThis.window=boot.window; globalThis.document=boot.window.document
const built = await build({entryPoints:['src/components/ScheduleViolations.jsx'],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime']})
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
after(()=>boot.window.close())
test('violation filters, manager modal and retry-safe request', async t => {
 const dom=new JSDOM('<div id="root"/>',{pretendToBeVisual:true});globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true};dom.window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'));t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 let saved=0, fail=true;const calls=[]
 const request=async(path,options)=>{calls.push({path,options});if(options){if(fail){fail=false;throw Error('Network failed')}return {message:'Đã lưu'}}return {rows:[{id:'one',updated_at:'2026-10-06T03:00:00Z',is_manual:true,employee_name:'Yên Linh',employee_username:'linh',violation_date:'2026-10-06',reason:'Đồng phục',amount:50000},{id:'two',employee_name:'Mạnh Đạt',employee_username:'dat',violation_date:'2026-10-05',reason:'Khác',amount:10000}]}}
 const render=canEdit=>act(async()=>root.render(React.createElement(mod.exports.default,{department:'letan',employees:[{username:'linh',full_name:'Yên Linh'}],canEdit,canManage:canEdit,request,onSaved:()=>saved++})))
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
})
