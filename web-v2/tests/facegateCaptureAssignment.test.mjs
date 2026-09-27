import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'
const built=await build({stdin:{contents:`import React,{act} from 'react';import{createRoot}from'react-dom/client';import Page from './src/pages/CheckinHistoryPage';import Assignment from './src/components/FacegateCaptureAssignment';window.act=act;window.mount=(kind,permissions)=>{window.root=createRoot(document.getElementById('root'));window.root.render(kind==='page'?<Page user={{permissions}}/>:<Assignment capture={window.capture} onClose={()=>window.closed++} onSaved={u=>window.saved.push(u)}/>)};`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'mock',setup(b){
 b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onResolve({filter:/\/lib\/staffSecurityApi$/},()=>({path:'face',namespace:'mock'}));b.onResolve({filter:/\/pages\/EmployeeIdentityPanel$/},()=>({path:'editor',namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},({path})=>({resolveDir:process.cwd(),loader:'jsx',contents:path==='api'?'export const veraApi=window.api':path==='face'?'export const faceIdApi=window.face':'export function IdentityImageEditor(p){window.editorProps=p;return <button onClick={()=>p.onConfirm(window.processed)}>Dùng ảnh đã chỉnh</button>}' }))
}}]})
const record={event_id:16465,occurred_at:'2026-09-26T18:42:58+07:00',image_available:true,image_ref:{file_type:1,file_index:0,file_position:123,time:'2026-09-26/18:42:58'}}
async function setup(ctx,{kind='assignment',permissions={},face={},api={}}={}){
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,channels=[]
 w.MessageChannel=class extends MessageChannel{constructor(){super();channels.push(this)}}
 w.IS_REACT_ACT_ENVIRONMENT=true;w.closed=0;w.saved=[];w.urls=[];w.revoked=[]
 w.URL.createObjectURL=blob=>{const url=`blob:${w.urls.length}`;w.urls.push({blob,url});return url};w.URL.revokeObjectURL=url=>w.revoked.push(url)
 w.capture={record,blob:new w.Blob(['original'],{type:'image/jpeg'})};w.processed=new w.Blob(['cropped'],{type:'image/webp'})
 w.face={assignmentEmployees:async()=>({employees:[{username:'An An',full_name:'Đinh Thúy An'},{username:'Ánh Thử',full_name:'Nguyễn Ánh Thử'}]}),metadata:async()=>({photo:null,can_manage:true}),...face}
 w.api={checkinHistory:async()=>({records:[record],options:{statuses:[],types:[]}}),facegateCaptureImage:async()=>w.capture.blob,...api}
 w.eval(built.outputFiles[0].text);await w.act(async()=>w.mount(kind,permissions))
 ctx.after(async()=>{await w.act(async()=>w.root.unmount());channels.forEach(c=>{c.port1.close();c.port2.close()});w.close()})
 const button=label=>[...w.document.querySelectorAll('button')].find(b=>b.textContent.trim()===label)
 const click=async label=>{assert.ok(button(label),label);await w.act(async()=>button(label).click())}
 const change=async(node,value)=>{await w.act(async()=>{Object.getOwnPropertyDescriptor(node.tagName==='SELECT'?w.HTMLSelectElement.prototype:w.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new w.Event(node.tagName==='SELECT'?'change':'input',{bubbles:true}))})}
 const select=async name=>change(w.document.querySelector('.capture-assignment-dialog select'),name)
 const confirm=async()=>{await w.act(async()=>w.document.querySelector('.capture-assignment-confirm input').click())}
 return{w,button,click,change,select,confirm}
}
test('capture image and roster load only on click; authorized choice uses viewed image; viewer cannot assign',async ctx=>{
 let images=0,roster=0
 const p=await setup(ctx,{kind:'page',permissions:{employee_face_id_manage:true},face:{assignmentEmployees:async()=>{roster++;return{employees:[]}}},api:{facegateCaptureImage:async()=>{images++;return new Blob(['capture'],{type:'image/jpeg'})}}})
 await p.change([...p.w.document.querySelectorAll('select')].find(s=>s.querySelector('option[value=capture]')),'capture');await p.click('Xem lịch sử')
 assert.equal(images,0);assert.equal(roster,0);assert.equal(p.button('Chọn ảnh cho nhân viên'),undefined)
 await p.click('Xem ảnh');assert.equal(images,1);await p.click('Chọn ảnh cho nhân viên');assert.equal(roster,1);assert.equal(images,1)
 assert.ok(p.w.document.querySelector('[role=dialog]'));assert.match(p.w.document.body.textContent,/26-09-2026 18:42:58/)
 await p.click('Hủy');assert.equal(p.w.document.querySelector('[role=dialog]'),null);assert.equal(p.w.document.querySelector('select option[value=capture]').parentNode.value,'capture')
 const viewer=await setup(ctx,{kind:'page'});await viewer.change([...viewer.w.document.querySelectorAll('select')].find(s=>s.querySelector('option[value=capture]')),'capture')
 await viewer.click('Xem lịch sử');await viewer.click('Xem ảnh');assert.equal(viewer.button('Chọn ảnh cho nhân viên'),undefined)
})
test('Unicode employee selection, crop and confirmation precede conditional save',async ctx=>{
 const writes=[],p=await setup(ctx,{face:{metadata:async()=>({photo:{sha256:'old'},can_manage:true}),identityBlob:async()=>new Blob(['old']),assignCapturePhoto:async(...args)=>writes.push(args)}})
 assert.equal(p.button('Lưu ảnh FACE ID').disabled,true);await p.change(p.w.document.querySelector('input[type=search]'),'anh thu');assert.match(p.w.document.querySelector('select').textContent,/Ánh Thử · Nguyễn Ánh Thử/)
 await p.select('Ánh Thử');assert.ok(p.w.document.querySelector('img[alt="Ảnh FACE ID hiện có của Ánh Thử"]'))
 await p.click('Cắt / xoay ảnh (tùy chọn)');assert.equal(p.w.editorProps.aspectRatio,null);assert.equal(p.w.editorProps.allowOriginal,undefined);await p.click('Dùng ảnh đã chỉnh');assert.equal(writes.length,0)
 await p.confirm();await p.click('Lưu ảnh FACE ID');assert.equal(writes.length,1);assert.equal(writes[0][0],'Ánh Thử');assert.equal(writes[0][1],p.w.processed);assert.equal(writes[0][2],'old');assert.deepEqual([...p.w.saved],['Ánh Thử'])
})
test('conflict retains draft and requires re-read; network retry keeps same precondition',async ctx=>{
 let version='old',writes=0;const expected=[]
 const p=await setup(ctx,{face:{metadata:async()=>({photo:{sha256:version},can_manage:true}),identityBlob:async()=>new Blob(['old']),assignCapturePhoto:async(_u,_b,sha)=>{expected.push(sha);if(++writes===1)throw Object.assign(Error('Ảnh đã đổi'),{status:409});if(writes===2)throw Error('Lỗi mạng')}}})
 await p.select('An An');await p.click('Cắt / xoay ảnh (tùy chọn)');await p.click('Dùng ảnh đã chỉnh');await p.confirm();await p.click('Lưu ảnh FACE ID');assert.match(p.w.document.body.textContent,/Ảnh đã đổi/);assert.equal(p.button('Lưu ảnh FACE ID').disabled,true)
 version='new';await p.click('Kiểm tra lại ảnh hiện có');assert.equal(p.button('Lưu ảnh FACE ID').disabled,true);assert.match(p.w.document.body.textContent,/Ảnh mới đã chỉnh/)
 await p.confirm();await p.click('Lưu ảnh FACE ID');assert.match(p.w.document.body.textContent,/Lỗi mạng/);await p.click('Lưu ảnh FACE ID');assert.deepEqual(expected,['old','new','new']);assert.deepEqual([...p.w.saved],['An An'])
})
test('denial and cancel never write; empty existing photo has create-only precondition',async ctx=>{
 let writes=0,expected='unset';const p=await setup(ctx,{face:{metadata:async()=>({can_manage:false,photo:null}),assignCapturePhoto:async()=>writes++}})
 await p.select('An An');assert.match(p.w.document.body.textContent,/chưa có quyền/);assert.equal(p.button('Lưu ảnh FACE ID').disabled,true);await p.click('Hủy');assert.equal(writes,0);assert.equal(p.w.closed,1)
 const q=await setup(ctx,{face:{assignCapturePhoto:async(_u,_b,sha)=>{expected=sha}}});await q.select('An An');await q.click('Cắt / xoay ảnh (tùy chọn)');await q.click('Dùng ảnh đã chỉnh');await q.confirm();await q.click('Lưu ảnh FACE ID');assert.equal(expected,null)
})
test('transport sends exact optimistic headers for create and replacement',async()=>{
 const result=await build({stdin:{contents:"import {faceIdApi} from './src/lib/staffSecurityApi';window.faceApi=faceIdApi",resolveDir:process.cwd(),loader:'js'},bundle:true,write:false,format:'iife',define:{'import.meta.env.VITE_VERA_API_BASE_URL':'"https://api.example.test"'},plugins:[{name:'session',setup(b){b.onResolve({filter:/\/supabase$/},()=>({path:'session',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const getCurrentSession=async()=>({access_token:"synthetic"})'}))}}]})
 const calls=[],w={};new Function('window','fetch','Headers',result.outputFiles[0].text)(w,async(url,options)=>{calls.push({url,options});return{ok:true,json:async()=>({ok:true})}},Headers)
 const blob=new Blob(['BMdevice-raster'],{type:'image/bmp'});await w.faceApi.assignCapturePhoto('Ánh Thử',blob,null);await w.faceApi.assignCapturePhoto('Ánh Thử',blob,'hash')
 assert.match(calls[0].url,/%C3%81nh%20Th%E1%BB%AD\/face-id\/capture-photo$/);assert.equal(calls[0].options.headers.get('If-None-Match'),'*');assert.equal(calls[1].options.headers.get('If-Match'),'"hash"');assert.equal(calls[1].options.body,blob)
 assert.equal(calls[0].options.headers.get('Content-Type'),'image/bmp');assert.equal(calls[0].options.headers.get('Authorization'),'Bearer synthetic')
})

test('confirmed capture saves original without compulsory editing',async ctx=>{
 const writes=[],p=await setup(ctx,{face:{assignCapturePhoto:async(...args)=>writes.push(args)}})
 await p.select('An An');assert.equal(p.button('Lưu ảnh FACE ID').disabled,true)
 await p.confirm();await p.click('Lưu ảnh FACE ID')
 assert.equal(p.w.editorProps,undefined);assert.equal(writes.length,1)
 assert.equal(writes[0][1],p.w.capture.blob);assert.equal(writes[0][2],null)
})
