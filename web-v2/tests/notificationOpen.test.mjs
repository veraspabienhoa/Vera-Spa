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
const bundle=await build({stdin:{contents:"import React from 'react';import {createRoot} from 'react-dom/client';import Inbox from './src/components/NotificationInbox';window.mount=()=>createRoot(document.getElementById('root')).render(<Inbox showTrigger={false}/>);",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const veraApi=window.api;',loader:'js'}))}}]})
const tick=()=>new Promise(r=>setTimeout(r,60))
for(const denied of [false,true]) test(`detail authorization denied=${denied}`,async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://app.veraspa.vn/?notification=42',runScripts:'dangerously',pretendToBeVisual:true});let read;
 dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true};
 dom.window.api={notificationDetail:async id=>{if(denied)throw new Error('No access');return {id,payload:{title:'Title',body:'Full detail'},created_at:'2026-09-24T14:00:00Z'}},readNotification:async id=>{read=id}};
 dom.window.eval(bundle.outputFiles[0].text);dom.window.mount();await tick();await tick();
 assert.match(dom.window.document.body.textContent,denied?/No access/:/Full detail/);assert.equal(read,denied?undefined:'42');assert.equal(dom.window.document.querySelector('dialog').open,true);
 dom.window.document.querySelector('button').click();await tick();assert.equal(dom.window.location.search,'');dom.window.close();
})
