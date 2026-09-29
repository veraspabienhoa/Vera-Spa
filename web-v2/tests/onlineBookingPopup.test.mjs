import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Popup from './src/components/OnlineBookingPopup';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=user=>act(async()=>root.render(<Popup user={user} onOpen={()=>window.opens++}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader:'jsx' },
  bundle:true, write:false, format:'iife', jsx:'automatic', loader:{'.css':'empty'},
  plugins:[{name:'mock-api',setup(b){
    b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}))
    b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:`export const veraApi={onlineBookingsUnread:async()=>{window.reads++;return {rows:window.rows}},onlineBookingSeen:async id=>{if(window.fail)throw Error('Mất kết nối');window.seen.push(id)}};`}))
  }}],
})
async function mount(role='letan') {
  const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true})
  const w=dom.window
  w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
  w.IS_REACT_ACT_ENVIRONMENT=true;w.opens=0;w.reads=0;w.seen=[]
  w.rows=[{id:1,kind:'booking',customer_name:'<script>Test</script>',phone:'0900000000',appointment_date:'2026-09-30',appointment_time:'14:30',service:'VIP',guests:2}]
  w.eval(built.outputFiles[0].text);await w.mount({id:'a',role});return dom
}
test('popup shows all booking fields safely, persists acknowledgement and opens inbox',async()=>{
  const dom=await mount(),w=dom.window
  try {
    const text=w.document.body.textContent
    for(const value of ['<script>Test</script>','0900000000','30-09-2026','14:30','VIP','2']) assert.ok(text.includes(value))
    assert.equal(w.document.querySelector('script'),null)
    w.fail=true
    await w.act(async()=>w.document.querySelectorAll('button')[0].click())
    assert.ok(w.document.querySelector('[role="alert"]'));assert.ok(w.document.querySelector('aside'))
    w.fail=false
    await w.act(async()=>w.document.querySelectorAll('button')[1].click())
    assert.equal(w.seen[0],1);assert.equal(w.opens,1);assert.equal(w.document.querySelector('aside'),null)
  } finally {await w.unmount();w.close()}
})
test('unauthorized roles do not fetch; contact does not invent an appointment',async()=>{
  const dom=await mount('nhanvien'),w=dom.window
  try {
    assert.equal(w.reads,0)
    w.rows=[{id:2,kind:'contact',customer_name:'Test',phone:'0900000000',message:'Xin tư vấn'}]
    await w.mount({id:'a',role:'admin'})
    assert.ok(w.document.body.textContent.includes('Xin tư vấn'))
    assert.equal((w.document.body.textContent.match(/Chưa cung cấp/g)||[]).length,4)
    await w.mount({id:'a',role:'admin',must_change_password:true})
    assert.equal(w.document.querySelector('aside'),null)
  } finally {await w.unmount();w.close()}
})
