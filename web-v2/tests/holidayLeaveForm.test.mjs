import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const compiled = await build({ stdin: { contents: `import React,{act} from 'react'; import {createRoot} from 'react-dom/client'; import HolidayLeaveSection from './src/pages/HolidayLeaveSection'; const root=createRoot(document.getElementById('root')); window.act=act; window.mount=()=>act(async()=>root.render(<HolidayLeaveSection/>)); window.unmount=()=>act(async()=>root.unmount());`, loader:'jsx', resolveDir:process.cwd() }, bundle:true, write:false, format:'iife', jsx:'automatic', loader:{'.css':'empty'}, plugins:[{name:'api-fixture',setup(b){
 b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'fixture'}));b.onResolve({filter:/\/lib\/systemDialogs$/},()=>({path:'dialogs',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},arg=>({loader:'js',contents:arg.path==='api'?'export const veraApi=window.api;':'export const confirmDialog=async message=>window.confirm(message); export const alertDialog=async message=>window.messages.push(message);'}));
}}] })
const tick = () => new Promise(resolve => setTimeout(resolve,20))
async function mount(canRegister=true) {
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window
 w.IS_REACT_ACT_ENVIRONMENT=true;w.messages=[];w.confirm=()=>true;w.writes=[]
 w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 const data={registrations:[],can_register:canRegister,can_cancel:false,employees:canRegister?[{username:'An',full_name:'An Test',department:'locker'},{username:'Bình',full_name:'Binh Test',department:'letan'}]:[],departments:[{code:'locker',name:'Locker'},{code:'letan',name:'Lễ tân'}]}
 w.api={holidayLeave:async()=>data,registerHolidayLeave:async body=>{w.writes.push(body);return {message:'Đã lưu'}},cancelHolidayLeave:async()=>{throw Error('not allowed')}}
 w.eval(compiled.outputFiles[0].text);await w.mount();await w.act(tick);return dom
}
async function change(w,element,value){await w.act(async()=>{Object.getOwnPropertyDescriptor(element.tagName==='SELECT'?w.HTMLSelectElement.prototype:w.HTMLInputElement.prototype,'value').set.call(element,value);element.dispatchEvent(new w.Event(element.tagName==='SELECT'?'change':'input',{bubbles:true}))})}
test('Permission denied hides write form',async()=>{const dom=await mount(false),w=dom.window;assert.equal(w.document.querySelector('form'),null);assert.match(w.document.body.textContent,/chưa được cấp quyền/);await w.unmount();w.close()})
test('Form confirms before submitting all-employee day registration',async()=>{
 const dom=await mount(),w=dom.window,note=[...w.document.querySelectorAll('input')].find(input=>input.maxLength===1000)
 await change(w,note,'Lễ Test');w.confirm=()=>false
 await w.act(async()=>w.document.querySelector('form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true})));assert.equal(w.writes.length,0)
 w.confirm=()=>true;await w.act(async()=>{w.document.querySelector('form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true}));await tick()})
 assert.equal(w.writes.length,1);assert.equal(w.writes[0].scope,'all');assert.equal(w.writes[0].mode,'day');assert.equal(w.writes[0].dates.length,1);assert.equal(w.writes[0].note,'Lễ Test');assert.match(w.writes[0].request_id,/^[0-9a-f-]{36}$/)
 await w.unmount();w.close()
})
test('HR department selector and paired date/time inputs',async()=>{
 const dom=await mount(),w=dom.window;let selects=[...w.document.querySelectorAll('form select')]
 await change(w,selects[0],'departments');assert.equal(w.document.querySelectorAll('form input[type=checkbox]').length,2)
 await w.act(async()=>w.document.querySelector('form input[type=checkbox]').click());selects=[...w.document.querySelectorAll('form select')]
 await change(w,selects[1],'hours');assert.equal(w.document.querySelectorAll('form input[type=time]').length,2);assert.equal(w.document.querySelectorAll('form .vera-datetime-input').length,2);assert.match(w.document.querySelector('form').textContent,/1 nhân viên/)
 await w.unmount();w.close()
})
