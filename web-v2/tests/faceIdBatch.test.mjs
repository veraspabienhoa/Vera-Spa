import test from 'node:test'
import assert from 'node:assert/strict'
import { uploadFaceBatch, validateBatchFiles } from '../src/lib/faceIdBatch.js'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const built = await build({stdin:{contents:"import React from 'react'; import {createRoot} from 'react-dom/client'; import Bulk from './src/pages/FaceIdBulkUpload'; window.mount=()=>createRoot(document.getElementById('root')).render(<Bulk/>);",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){
 b.onResolve({filter:/\/lib\/staffSecurityApi$/},()=>({path:'api',namespace:'mock'})); b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const faceIdApi=window.api; export const staffSecurityApi={};',loader:'js'}))
}}]})
const tick=()=>new Promise(resolve=>setTimeout(resolve,40))
const button=(dom,text)=>[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.includes(text))

test('file count and aggregate size bounds',()=>{
  assert.throws(()=>validateBatchFiles(Array(51).fill({size:1})))
  assert.throws(()=>validateBatchFiles([{size:101*1024*1024}]))
  assert.doesNotThrow(()=>validateBatchFiles([{size:1024}]))
})

test('uploads are sequential, successes skipped on retry, auth failure stops batch',async()=>{
  const rows=[0,1,2].map(id=>({id,selected:true,blob:{},state:'ready'}))
  const update=(id,patch)=>Object.assign(rows[id],patch)
  let inFlight=0, maximum=0, calls=[]
  const upload=async row=>{inFlight++;maximum=Math.max(maximum,inFlight);calls.push(row.id);await tick();inFlight--;if(row.id===1)throw Error('retry')}
  await uploadFaceBatch(rows,upload,update)
  assert.equal(maximum,1);assert.deepEqual(calls,[0,1,2]);assert.equal(rows[0].state,'saved');assert.equal(rows[1].state,'error')
  calls=[]
  await uploadFaceBatch(rows,async row=>calls.push(row.id),update)
  assert.deepEqual(calls,[1]);assert.ok(rows.every(row=>row.state==='saved'))
  rows.forEach(row=>Object.assign(row,{selected:true,state:'ready'}));calls=[]
  await uploadFaceBatch(rows,async row=>{calls.push(row.id);throw Object.assign(Error('denied'),{status:403})},update)
  assert.deepEqual(calls,[0])
})

test('preview preserves full image, existing photos need selection, and unmatched files cannot upload',async()=>{
  const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true})
  let uploaded=[],draws=[]
  dom.window.api={batchPlan:async names=>({records:names.map((filename,id)=>({filename,status:id===2?'not_found':'ready',username:id===2?null:['An','Nhi'][id],existing_sha256:id===1?'old':null}))}),uploadBatchPhoto:async row=>uploaded.push(row.username)}
  dom.window.URL.createObjectURL=()=>`blob:${Math.random()}`;dom.window.URL.revokeObjectURL=()=>{}
  dom.window.Image=class{naturalWidth=1600;naturalHeight=900;set src(_value){setTimeout(()=>this.onload(),0)}}
  dom.window.HTMLCanvasElement.prototype.getContext=()=>({fillRect(){},drawImage(...args){draws.push(args.slice(1))}})
  dom.window.HTMLCanvasElement.prototype.toBlob=function(cb,type){cb(new dom.window.Blob(['compressed'],{type}))}
  dom.window.eval(built.outputFiles[0].text);dom.window.mount();await tick()
  const input=dom.window.document.querySelector('input[type=file]')
  Object.defineProperty(input,'files',{value:['An.jpg','Nhi.jpg','Sai.jpg'].map(name=>new dom.window.File(['photo'],name,{type:'image/jpeg'}))})
  input.dispatchEvent(new dom.window.Event('change',{bubbles:true}));await tick();await tick()
  const boxes=[...dom.window.document.querySelectorAll('input[type=checkbox]')]
  assert.equal(boxes[0].checked,true);assert.equal(boxes[1].checked,false);assert.equal(boxes[2].disabled,true)
  assert.ok(draws.every(([x,y,w,h])=>x===0&&y>0&&w===900&&h<1200))
  button(dom,'Lưu 1 ảnh đã chọn').click();await tick()
  assert.deepEqual(uploaded,['An'])
  assert.equal(boxes[0].disabled,true)
  boxes[1].click();await tick();button(dom,'Lưu 1 ảnh đã chọn').click();await tick()
  assert.deepEqual(uploaded,['An','Nhi'])
  dom.window.close()
})
