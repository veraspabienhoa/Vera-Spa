import test,{after} from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React,{act} from 'react'
import {JSDOM} from 'jsdom'
const bootstrap=new JSDOM('<body/>');globalThis.window=bootstrap.window;globalThis.document=bootstrap.window.document;after(()=>bootstrap.window.close())
const built=await build({stdin:{contents:`export {default as Panel} from './src/pages/WorkScheduleViolations';export * from './src/lib/workScheduleViolations'`,resolveDir:process.cwd()},bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',loader:{'.css':'empty'},external:['react','react-dom','react/jsx-runtime'],plugins:[{name:'api',setup(b){b.onResolve({filter:/\/api$/},()=>({path:'mock',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const veraApi={leaveRecords:(...args)=>globalThis.leaveRecords(...args),createLeave:body=>globalThis.createLeave(body)}'}))}}]})
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
const {Panel,loadViolationRecords,isViolation,violationMonthRange}=mod.exports

test('canonical types and cross-year ranges exclude ordinary leave',async()=>{
 assert.equal(isViolation({leave_type:'Vi phạm'}),true);assert.equal(isViolation({leave_type:'Có phép',penalty:500}),false);assert.deepEqual(violationMonthRange('2028-02'),{start:'2028-02-01',end:'2028-02-29'})
 const ranges=[];globalThis.leaveRecords=async(start,end)=>{ranges.push([start,end]);return {records:[{leave_type:'Vi phạm',leave_date:start},{leave_type:'Không phép',leave_date:start}]}}
 assert.equal((await loadViolationRecords('2026-12-20','2027-01-05')).length,2);assert.deepEqual(ranges,[['2026-12-20','2026-12-31'],['2027-01-01','2027-01-05']]);await assert.rejects(()=>loadViolationRecords('2027-01-02','2027-01-01'));await assert.rejects(()=>loadViolationRecords('2025-01-01','2026-02-01'))
})

test('manager submits one manual penalty; other roles cannot open entry',async t=>{
 const dom=new JSDOM('<body><div id="root"/></body>',{url:'https://example.test'});globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true;window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
 const records=[{record_uid:'a',employee_name:'dat',leave_date:'2026-10-06',leave_type:'Vi phạm',leave_reason:'Lỗi vi phạm khác',penalty:50000},{record_uid:'b',employee_name:'other',leave_date:'2026-10-06',leave_type:'Vi phạm',penalty:90000}],submitted=[],loads=[]
 globalThis.leaveRecords=async(start,end)=>{loads.push([start,end]);return {records}};globalThis.createLeave=async body=>{submitted.push(body);return {}}
 const request=async()=>({violations:[{name:'Lỗi vi phạm khác',requires_manual_penalty:true},{name:'Lỗi cố định',penalty:10000}]})
 const {createRoot}=await import('react-dom/client');const root=createRoot(document.querySelector('#root'));t.after(async()=>{await act(()=>root.unmount());dom.window.close();delete globalThis.window;delete globalThis.document})
 const props={user:{role:'quanly',permissions:{employee_penalty_view:true}},employees:[{username:'dat',system_name:'Ngô Sĩ Đạt'}],request,revision:0,onSaved:()=>{}}
 await act(async()=>root.render(React.createElement(Panel,props)));assert.equal(document.querySelectorAll('tbody tr').length,1);assert.match(document.querySelector('tbody').textContent,/06-10-2026/)
 const click=async text=>{const button=[...document.querySelectorAll('button')].find(item=>item.textContent===text);assert.ok(button,text);await act(async()=>button.click())}
 await click('Tháng trước');assert.equal(loads.at(-1)[0],loads.at(-1)[1].slice(0,7)+'-01');await click('+ Nhập phạt vi phạm');assert.ok(document.querySelector('dialog').open)
 const change=async(node,value)=>act(async()=>{Object.getOwnPropertyDescriptor(node.tagName==='SELECT'?window.HTMLSelectElement.prototype:window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event(node.tagName==='SELECT'?'change':'input',{bubbles:true}))})
 await change(document.querySelector('.schedule-violation-filters input[type=search]'),'khong co');assert.match(document.querySelector('tbody').textContent,/Không có vi phạm/);await change(document.querySelector('.schedule-violation-filters input[type=search]'),'ngo si dat');assert.equal(document.querySelectorAll('tbody tr').length,1)
 const selects=document.querySelectorAll('dialog select');await change(selects[0],'dat');await change(selects[1],'Lỗi vi phạm khác');await change(document.querySelector('dialog .vera-money-input'),'50.000')
 await act(async()=>{const form=document.querySelector('dialog form');form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}));form.dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true}))});assert.equal(submitted.length,1);assert.equal(submitted[0].manual_penalty,50000);assert.equal(submitted[0].employee_name,'dat');assert.equal(document.querySelector('dialog'),null)
 await click('+ Nhập phạt vi phạm');const fixedSelects=document.querySelectorAll('dialog select');await change(fixedSelects[0],'dat');await change(fixedSelects[1],'Lỗi cố định');assert.equal(document.querySelector('dialog .vera-money-input'),null);await click('+ Ghi phạt vi phạm');assert.equal(submitted.length,2);assert.equal(Object.hasOwn(submitted[1],'manual_penalty'),false)
 await act(async()=>root.render(React.createElement(Panel,{...props,user:{role:'letan'}})));assert.equal([...document.querySelectorAll('button')].some(item=>item.textContent==='+ Nhập phạt vi phạm'),false);assert.equal(document.querySelectorAll('th').length,4)
})
