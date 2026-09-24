import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({stdin:{contents:"import React from 'react'; import {createRoot} from 'react-dom/client'; import {FaceIdCard} from './src/pages/EmployeeIdentityPanel'; window.mount=()=>createRoot(document.getElementById('root')).render(<FaceIdCard username='worker'/>);",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){
 b.onResolve({filter:/\/lib\/staffSecurityApi$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const faceIdApi=window.api; export const staffSecurityApi={};',loader:'js'}))
}}]})
const tick=()=>new Promise(resolve=>setTimeout(resolve,40))
async function mount(api){const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});dom.window.api=api;dom.window.URL.createObjectURL=()=> 'blob:test';dom.window.URL.revokeObjectURL=()=>{};dom.window.eval(built.outputFiles[0].text);dom.window.mount();await tick();return dom}
const button=(dom,text)=>[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.includes(text))
test('view-only cannot mutate face photo',async()=>{const dom=await mount({metadata:async()=>({can_manage:false,photo:{size_bytes:20}}),identityBlob:async()=>new Blob(['x'])});assert.equal(button(dom,'Thay ảnh').disabled,true);assert.equal(button(dom,'Xóa').disabled,true);assert.equal(button(dom,'Crop / Xoay').disabled,true);assert.equal(button(dom,'Từ ảnh đại diện'),undefined);dom.window.close()})
test('manager selects capture explicitly with identity warning',async()=>{const dom=await mount({metadata:async()=>({can_manage:true,photo:null}),captures:async()=>({records:[{event_id:7,occurred_at:'2026-09-24T10:00:00+07:00'}]})});assert.equal(button(dom,'Tải ảnh').disabled,false);assert.ok(button(dom,'Từ ảnh đại diện'));button(dom,'Từ ảnh chụp trên FaceID').click();await tick();assert.ok(dom.window.document.body.textContent.includes('chưa xác minh danh tính'));assert.ok(button(dom,'#7'));dom.window.close()})
test('denied permission exposes no controls',async()=>{const dom=await mount({metadata:async()=>{throw Object.assign(new Error('denied'),{status:403})}});assert.equal(dom.window.document.querySelectorAll('button').length,0);dom.window.close()})
