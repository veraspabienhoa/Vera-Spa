import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({stdin:{contents:"import React from 'react'; import {createRoot} from 'react-dom/client'; import {FaceIdCard} from './src/pages/EmployeeIdentityPanel'; window.mount=()=>createRoot(document.getElementById('root')).render(<FaceIdCard username='worker'/>);",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){
 b.onResolve({filter:/\/lib\/staffSecurityApi$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const faceIdApi=window.api; export const staffSecurityApi={};',loader:'js'}))
}}]})
const tick=()=>new Promise(resolve=>setTimeout(resolve,40))
async function mount(api){const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});dom.window.api={captures:async()=>({records:[]}),capture:async()=>new dom.window.Blob(['photo'],{type:'image/jpeg'}),...api};dom.window.URL.createObjectURL=()=> 'blob:test';dom.window.URL.revokeObjectURL=()=>{};dom.window.eval(built.outputFiles[0].text);dom.window.mount();await tick();return dom}
const button=(dom,text)=>[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.includes(text))
test('view-only cannot mutate face photo',async()=>{const dom=await mount({metadata:async()=>({can_manage:false,photo:{size_bytes:20}}),identityBlob:async()=>new Blob(['x'])});assert.equal(button(dom,'Thay ảnh').disabled,true);assert.equal(button(dom,'Xóa').disabled,true);assert.equal(button(dom,'Crop / Xoay').disabled,true);assert.equal(button(dom,'Từ ảnh đại diện'),undefined);dom.window.close()})
test('manager selects capture explicitly with identity warning',async()=>{const dom=await mount({metadata:async()=>({can_manage:true,photo:null}),captures:async()=>({records:[{event_id:7,occurred_at:'2026-09-24T10:00:00+07:00'}]})});assert.equal(button(dom,'Tải ảnh').disabled,false);assert.ok(button(dom,'Từ ảnh đại diện'));button(dom,'Từ ảnh chụp trên FaceID').click();await tick();assert.ok(dom.window.document.body.textContent.includes('chưa xác minh danh tính'));assert.ok(button(dom,'#7'));dom.window.close()})
test('denied permission exposes no controls',async()=>{const dom=await mount({metadata:async()=>{throw Object.assign(new Error('denied'),{status:403})}});assert.equal(dom.window.document.querySelectorAll('button').length,0);dom.window.close()})

test('camera captures full native frame without 3:4 cropping',async()=>{
 const dom=await mount({metadata:async()=>({can_manage:true,photo:null})}),w=dom.window
 let constraints,drawn
 Object.defineProperty(w.navigator,'mediaDevices',{value:{getUserMedia:async value=>{constraints=value;return{getTracks:()=>[{stop(){}}]}}}})
 w.HTMLMediaElement.prototype.play=async()=>{}
 w.HTMLCanvasElement.prototype.getContext=()=>({drawImage(...args){drawn=args.slice(1)}})
 w.HTMLCanvasElement.prototype.toBlob=function(done,type){done(new w.Blob(['photo'],{type}))}
 button(dom,'Chụp ảnh').click();await tick()
 assert.equal(constraints.video.aspectRatio,undefined)
 const video=w.document.querySelector('video')
 Object.defineProperty(video,'videoWidth',{value:1280});Object.defineProperty(video,'videoHeight',{value:720})
 const shutter=[...w.document.querySelectorAll('.identity-camera-card button')].find(b=>b.textContent.includes('Chụp ảnh'))
 shutter.click();await tick()
 assert.deepEqual(drawn,[0,0,1280,720,0,0,1280,720])
 assert.ok(button(dom,'Lưu ảnh gốc'))
 dom.window.close()
})

test('latest capture is previewed automatically and saving still requires explicit selection',async()=>{
 const requested=[],writes=[]
 const dom=await mount({metadata:async()=>({can_manage:true,photo:null}),captures:async()=>({records:[{event_id:7,occurred_at:'2026-09-27T09:00:00+07:00'},{event_id:9,occurred_at:'2026-09-27T11:00:00+07:00'},{event_id:8,occurred_at:'2026-09-27T10:00:00+07:00'}]}),capture:async(u,d,id)=>{requested.push(id);return new Blob(['photo'],{type:'image/jpeg'})},uploadIdentity:async()=>writes.push('write')})
 try {
  await tick()
  assert.deepEqual(requested,[9])
  assert.equal(dom.window.document.querySelector('.face-id-capture-preview img').alt,'Ảnh chụp FaceID #9')
  assert.equal(button(dom,'Lưu ảnh gốc'),undefined)
  assert.deepEqual(writes,[])
  button(dom,'#7').click();await tick()
  assert.equal(dom.window.document.querySelector('.face-id-capture-preview img').alt,'Ảnh chụp FaceID #7')
  assert.deepEqual(requested,[9,7])
  button(dom,'Chọn ảnh này').click();await tick()
  assert.ok(button(dom,'Lưu ảnh gốc'))
  assert.deepEqual(writes,[])
 } finally {dom.window.close()}
})

test('switching capture ignores a slower old response and revokes the preview URL',async()=>{
 let resolveOld,revoked=0
 const dom=await mount({metadata:async()=>({can_manage:true,photo:null}),captures:async()=>({records:[{event_id:9,occurred_at:'2026-09-27T11:00:00+07:00'},{event_id:7,occurred_at:'2026-09-27T09:00:00+07:00'}]}),capture:async(u,d,id)=>id===9?await new Promise(resolve=>{resolveOld=resolve}):new Blob(['old'],{type:'image/jpeg'})})
 try {
  dom.window.URL.revokeObjectURL=()=>revoked++
  button(dom,'#7').click();await tick()
  resolveOld(new Blob(['late'],{type:'image/jpeg'}));await tick()
  assert.equal(dom.window.document.querySelector('.face-id-capture-preview img').alt,'Ảnh chụp FaceID #7')
  button(dom,'Làm mới').click();await tick()
  assert.equal(revoked,1)
  assert.equal(dom.window.document.querySelector('.face-id-capture-preview img'),null)
 } finally {dom.window.close()}
})
