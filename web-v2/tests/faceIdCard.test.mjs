import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({stdin:{contents:"import React, {act} from 'react'; import {createRoot} from 'react-dom/client'; import {FaceIdCard} from './src/pages/EmployeeIdentityPanel'; const root=createRoot(document.getElementById('root')); window.act=act; window.mount=()=>act(async()=>root.render(<FaceIdCard username='worker' compact={window.compact}/>)); window.unmount=()=>act(async()=>root.unmount());",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){
 b.onResolve({filter:/\/lib\/staffSecurityApi$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const faceIdApi=window.api; export const staffSecurityApi={};',loader:'js'}))
}}]})
const tick=()=>new Promise(resolve=>setTimeout(resolve,40))
async function mount(api, compact = false){const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});dom.window.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}};dom.window.IS_REACT_ACT_ENVIRONMENT=true;dom.window.compact=compact;dom.window.api={identityBlob:async()=>new dom.window.Blob(['photo'],{type:'image/jpeg'}),enrollment:async()=>{throw Object.assign(new Error('denied'),{status:403})},captures:async()=>({records:[]}),capture:async()=>new dom.window.Blob(['photo'],{type:'image/jpeg'}),...api};dom.window.URL.createObjectURL=()=> 'blob:test';dom.window.URL.revokeObjectURL=()=>{};dom.window.eval(built.outputFiles[0].text);await dom.window.mount();return dom}
const button=(dom,text)=>[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.includes(text))
test('view-only cannot mutate face photo',async()=>{const dom=await mount({metadata:async()=>({can_manage:false,photo:{size_bytes:20}}),identityBlob:async()=>new Blob(['x'])});assert.equal(button(dom,'Thay ảnh'),undefined);assert.equal(button(dom,'Xóa'),undefined);assert.equal(button(dom,'Crop / Xoay'),undefined);assert.equal(button(dom,'Từ ảnh đại diện'),undefined);await dom.window.unmount();dom.window.close()})
test('manager selects capture explicitly with identity warning',async()=>{const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:null}),captures:async()=>({records:[{event_id:7,occurred_at:'2026-09-24T10:00:00+07:00'}]})});assert.equal(button(dom,'Tải ảnh').disabled,false);assert.ok(button(dom,'Từ ảnh đại diện'));await dom.window.act(async()=>button(dom,'Từ ảnh chụp trên FaceID').click());assert.ok(dom.window.document.body.textContent.includes('chưa được xác minh danh tính'));assert.ok(dom.window.document.querySelector('img[alt="Ảnh chụp FaceID #7"]'));await dom.window.unmount();dom.window.close()})
test('denied permission exposes no controls',async()=>{const dom=await mount({metadata:async()=>{throw Object.assign(new Error('denied'),{status:403})}});assert.equal(dom.window.document.querySelectorAll('button').length,0);await dom.window.unmount();dom.window.close()})

test('camera captures full native frame without 3:4 cropping',async()=>{
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:null})}),w=dom.window
 let constraints,drawn
 Object.defineProperty(w.navigator,'mediaDevices',{value:{getUserMedia:async value=>{constraints=value;return{getTracks:()=>[{stop(){}}]}}}})
 w.HTMLMediaElement.prototype.play=async()=>{}
 w.HTMLCanvasElement.prototype.getContext=()=>({drawImage(...args){drawn=args.slice(1)}})
 w.HTMLCanvasElement.prototype.toBlob=function(done,type){done(new w.Blob(['photo'],{type}))}
 await w.act(async()=>button(dom,'Chụp ảnh').click())
 assert.equal(constraints.video.aspectRatio,undefined)
 const video=w.document.querySelector('video')
 Object.defineProperty(video,'videoWidth',{value:1280});Object.defineProperty(video,'videoHeight',{value:720})
 const shutter=[...w.document.querySelectorAll('.identity-camera-card button')].find(b=>b.textContent.includes('Chụp ảnh'))
 await w.act(async()=>shutter.click())
 assert.deepEqual(drawn,[0,0,1280,720,0,0,1280,720])
 assert.ok(button(dom,'Lưu ảnh gốc'))
 await dom.window.unmount();dom.window.close()
})

test('latest capture is previewed automatically and saving still requires explicit selection',async()=>{
 const requested=[],writes=[]
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:null}),captures:async()=>({records:[{event_id:7,occurred_at:'2026-09-27T09:00:00+07:00'},{event_id:9,occurred_at:'2026-09-27T11:00:00+07:00'},{event_id:8,occurred_at:'2026-09-27T10:00:00+07:00'}]}),capture:async(u,d,id)=>{requested.push(id);return new Blob(['photo'],{type:'image/jpeg'})},uploadIdentity:async()=>writes.push('write')})
 try {
  await tick()
  assert.deepEqual(requested,[9,8,7])
  assert.equal(dom.window.document.querySelector('.face-id-capture-preview img').alt,'Ảnh chụp FaceID #9')
  assert.equal(button(dom,'Lưu ảnh gốc'),undefined)
  assert.deepEqual(writes,[])
  assert.equal(dom.window.document.querySelectorAll('.face-id-capture-preview img').length,3)
  await dom.window.act(async()=>button(dom,'Chọn ảnh này').click())
  assert.ok(button(dom,'Lưu ảnh gốc'))
  assert.deepEqual(writes,[])
 } finally {await dom.window.unmount();dom.window.close()}
})

test('gallery loads four images per page and navigates through every record',async()=>{
 const requested=[]
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:null}),captures:async()=>({records:Array.from({length:8},(_,i)=>({event_id:i,occurred_at:'2026-09-27T11:00:00+07:00'}))}),capture:async(u,d,id)=>{requested.push(id);return new Blob(['photo'],{type:'image/jpeg'})}})
 try {
  await tick();assert.deepEqual(requested,[7,6,5,4]);assert.equal(dom.window.document.querySelectorAll('.face-id-capture-preview img').length,4)
  assert.equal(button(dom,'Trang trước').disabled,true)
  await dom.window.act(async()=>button(dom,'Trang sau').click());await tick()
  assert.deepEqual(requested,[7,6,5,4,3,2,1,0]);assert.equal(dom.window.document.querySelectorAll('.face-id-capture-preview img').length,4)
  assert.equal(button(dom,'Trang sau').disabled,true)
  await dom.window.act(async()=>button(dom,'Trang trước').click());await tick()
  assert.ok(dom.window.document.querySelector('img[alt="Ảnh chụp FaceID #7"]'))
  await dom.window.act(async()=>button(dom,'Trang sau').click());await tick()
  await dom.window.act(async()=>button(dom,'Từ ảnh chụp trên FaceID').click());await tick()
  assert.equal(button(dom,'Trang trước').disabled,true)
  assert.ok(dom.window.document.querySelector('img[alt="Ảnh chụp FaceID #7"]'))
 }
 finally{await dom.window.unmount();dom.window.close()}
})

test('enrollment sends the saved photo hash only after confirmation',async()=>{
 const writes=[]
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'a'.repeat(64)}}),
  enrollment:async()=>({status:'not_registered',can_enroll:true}),
  enroll:async(...args)=>{writes.push(args);return{status:'verified',profile_id:123,photo_sha256:'a'.repeat(64)}}})
 try {
  assert.ok(button(dom,'Đăng ký lên máy'))
  dom.window.confirm=()=>false
  await dom.window.act(async()=>button(dom,'Đăng ký lên máy').click())
  assert.equal(writes.length,0)
  dom.window.confirm=()=>true
  await dom.window.act(async()=>button(dom,'Đăng ký lên máy').click())
  assert.equal(writes.length,1)
  assert.deepEqual(writes[0],['worker','a'.repeat(64),true])
  assert.equal(button(dom,'Đăng ký lên máy'),undefined)
  assert.ok(dom.window.document.body.textContent.includes('Hồ sơ 123'))
 }finally{await dom.window.unmount();dom.window.close()}
})

test('replacement updates the mapped profile without a manual confirmation prompt',async()=>{
 const writes=[]
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'b'.repeat(64)}}),
  enrollment:async()=>({status:'verified',profile_id:123,photo_sha256:'a'.repeat(64),can_replace:true,mapped_profile:{profile_id:123}}),
  enroll:async(...args)=>{writes.push(args);return{status:'verified',profile_id:123,photo_sha256:'b'.repeat(64)}}})
 try {
  assert.ok(button(dom,'Cập nhật ảnh trên máy'))
  dom.window.confirm=()=>{throw new Error('replacement should not request manual confirmation')}
  await dom.window.act(async()=>button(dom,'Cập nhật ảnh trên máy').click())
  assert.deepEqual(writes,[['worker','b'.repeat(64),false]])
  assert.ok(dom.window.document.body.textContent.includes('Đã thay ảnh trên hồ sơ hiện có'))
 } finally {await dom.window.unmount();dom.window.close()}
})

test('ambiguous device write exposes verification instead of duplicate registration',async()=>{
 let status='not_registered', writes=0,checks=0
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'a'.repeat(64)}}),
  enrollment:async()=>({status}),enroll:async()=>{writes++;status='unverified';throw new Error('Chưa xác minh')},
  verifyEnrollment:async()=>{checks++;return{status:'verified',profile_id:123,photo_sha256:'a'.repeat(64)}}})
 try{
  dom.window.confirm=()=>true
  await dom.window.act(async()=>button(dom,'Đăng ký lên máy').click())
  assert.equal(button(dom,'Đăng ký lên máy'),undefined)
  await dom.window.act(async()=>button(dom,'Kiểm tra lại kết quả').click())
  assert.equal(writes,1);assert.equal(checks,1)
 }finally{await dom.window.unmount();dom.window.close()}
})

test('a device blocker from another employee can be verified without assigning it to this photo',async()=>{
 let pending=true;const checks=[]
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'a'.repeat(64)}}),
  enrollment:async()=>({status:'not_registered',device_pending:pending?{employee_username:'other',status:'unverified'}:null}),
  verifyEnrollment:async(owner)=>{checks.push(owner);pending=false;return{status:'verified',profile_id:123}}})
 try{
  assert.equal(button(dom,'Đăng ký lên máy'),undefined)
  await dom.window.act(async()=>button(dom,'Kiểm tra lượt đang chặn máy').click())
  assert.deepEqual(checks,['other'])
  assert.ok(button(dom,'Đăng ký lên máy'))
  assert.ok(!dom.window.document.body.textContent.includes('Hồ sơ 123'))
 }finally{await dom.window.unmount();dom.window.close()}
})

test('a reconciled precommit failure permits registration again',async()=>{
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'a'.repeat(64)}}),
  enrollment:async()=>({status:'unverified'}),verifyEnrollment:async()=>({status:'rejected',error_code:'precommit_reconciled'})})
 try{
  await dom.window.act(async()=>button(dom,'Kiểm tra lại kết quả').click())
  assert.ok(button(dom,'Đăng ký lên máy'))
  assert.ok(dom.window.document.body.textContent.includes('mở lại đăng ký'))
 }finally{await dom.window.unmount();dom.window.close()}
})

test('focus automatically reconciles a stale device-wide blocker and releases buttons',async()=>{
 let pending=true;const checks=[]
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'a'.repeat(64)}}),
  enrollment:async()=>({status:'not_registered',device_pending:pending?{employee_username:'other',operation_id:'old',status:'running',stale:true}:null}),
  verifyEnrollment:async(owner)=>{checks.push(owner);pending=false;return{status:'rejected'}}})
 try{
  await dom.window.act(async()=>{dom.window.dispatchEvent(new dom.window.Event('focus'));await new Promise(r=>setTimeout(r,0))})
  assert.deepEqual(checks,['other'])
  assert.ok(button(dom,'Đăng ký lên máy'))
  assert.equal(button(dom,'Đăng ký lên máy').disabled,false)
  assert.match(dom.window.document.body.textContent,/Lượt gửi ảnh chưa thành công/)
  assert.doesNotMatch(dom.window.document.body.textContent,/Đã kiểm tra và cập nhật lượt đăng ký/)
 }finally{await dom.window.unmount();dom.window.close()}
})

test('automatic recovery is bounded and manual recovery remains available after device errors',async()=>{
 let checks=0
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:{size_bytes:20,sha256:'a'.repeat(64)}}),
  enrollment:async()=>({status:'unverified',operation_id:'pending'}),
  verifyEnrollment:async()=>{checks++;throw new Error('Máy chưa kết nối')}})
 try{
  for(let i=0;i<4;i++)await dom.window.act(async()=>{dom.window.dispatchEvent(new dom.window.Event('focus'));await new Promise(r=>setTimeout(r,0))})
  assert.equal(checks,3)
  assert.equal(button(dom,'Đăng ký lên máy'),undefined)
  assert.equal(button(dom,'Kiểm tra lại kết quả').disabled,false)
  await dom.window.act(async()=>button(dom,'Kiểm tra lại kết quả').click())
  assert.equal(checks,4)
 }finally{await dom.window.unmount();dom.window.close()}
})


test('compact dialog switches photo sources and keeps four captures per page',async()=>{
 const dom=await mount({metadata:async()=>({can_manage:true,can_view_device_tools:true,photo:null}),captures:async()=>({records:Array.from({length:5},(_,i)=>({event_id:i,occurred_at:'2026-10-06T10:00:00+07:00'}))})},true)
 try {
  assert.equal(button(dom,'Ảnh đã lưu').getAttribute('aria-pressed'),'true')
  await dom.window.act(async()=>button(dom,'Ảnh từ máy').click())
  assert.equal(button(dom,'Ảnh từ máy').getAttribute('aria-pressed'),'true')
  assert.ok(dom.window.document.querySelector('.face-id-view-captures'))
  assert.equal(dom.window.document.querySelectorAll('.face-id-capture-preview').length,4)
  await dom.window.act(async()=>button(dom,'Trang sau').click())
  assert.equal(dom.window.document.querySelectorAll('.face-id-capture-preview').length,1)
  await dom.window.act(async()=>button(dom,'Ảnh đã lưu').click())
  assert.ok(dom.window.document.querySelector('.face-id-view-photo'))
 }finally{await dom.window.unmount();dom.window.close()}
})
