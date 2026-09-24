import test from 'node:test'
import assert from 'node:assert/strict'
import vm from 'node:vm'
import {readFileSync} from 'node:fs'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'
const source=readFileSync('public/sw.js','utf8')
for(const [name,data,want] of [['detail',{notificationId:'42',url:'https://evil.test'},'https://app.veraspa.vn/?notification=42'],['legacy changes',{kind:'admin-system-change'},'https://app.veraspa.vn/?page=changes'],['external rejected',{url:'https://evil.test'},'https://app.veraspa.vn/']]) {
 test(`notification click ${name}`,async()=>{const handlers={};let opened,waiting;const self={location:{origin:'https://app.veraspa.vn'},addEventListener:(k,f)=>handlers[k]=f,clients:{matchAll:async()=>[],openWindow:async u=>{opened=u}}};vm.runInNewContext(source,{self,URL});handlers.notificationclick({notification:{data,close(){}},waitUntil:p=>waiting=p});await waiting;assert.equal(opened,want)})
}
const bundle=await build({stdin:{contents:"import React from 'react';import {createRoot} from 'react-dom/client';import Inbox from './src/components/NotificationInbox';window.mount=(showTrigger=false)=>createRoot(document.getElementById('root')).render(<Inbox showTrigger={showTrigger}/>);",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const veraApi=window.api;',loader:'js'}))}}]})
const tick=()=>new Promise(r=>setTimeout(r,60))
for(const denied of [false,true]) test(`detail authorization denied=${denied}`,async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://app.veraspa.vn/?notification=42',runScripts:'dangerously',pretendToBeVisual:true});let read;
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 dom.window.api={notificationDetail:async id=>{if(denied)throw new Error('No access');return {id,payload:{title:'Title',body:'Full detail'},created_at:'2026-09-24T14:00:00Z'}},readNotification:async id=>{read=id}};
 dom.window.eval(bundle.outputFiles[0].text);dom.window.mount();await tick();await tick();
 assert.match(dom.window.document.body.textContent,denied?/No access/:/Full detail/);assert.equal(read,undefined);assert.equal(dom.window.document.querySelector('dialog').open,true);
 dom.window.document.querySelector('button').click();await tick();assert.equal(dom.window.location.search,'');dom.window.close();
})
test('Admin explicitly marks viewed and the row disappears without showing VERA SPA',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://app.veraspa.vn/',runScripts:'dangerously',pretendToBeVisual:true});let read;
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 dom.window.api={notificationInbox:async()=>({notifications:[{id:7,payload:{title:'VERA SPA · Nhắc nghỉ giữa ca',body:'Còn 15 phút'},created_at:'2026-09-24T14:00:00Z'}]}),readNotification:async id=>{read=id}};
 dom.window.eval(bundle.outputFiles[0].text);dom.window.mount(true);await tick();
 dom.window.document.querySelector('.notification-inbox-trigger').click();await tick();
 assert.match(dom.window.document.querySelector('.notification-entry').textContent,/Nhắc nghỉ giữa ca/);
 assert.doesNotMatch(dom.window.document.querySelector('.notification-entry').textContent,/VERA SPA/);
 assert.equal(read,undefined);
 dom.window.document.querySelector('.notification-entry .notification-viewed').click();await tick();
 assert.equal(read,7);assert.equal(dom.window.document.querySelector('.notification-entry'),null);dom.window.close();
})
