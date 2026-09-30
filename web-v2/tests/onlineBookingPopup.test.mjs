import './bookingDateRange.test.mjs'
import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Popup from './src/components/OnlineBookingPopup';import Manual from './src/components/ManualOnlineBooking';import Upcoming from './src/components/UpcomingOnlineBookings';import Page from './src/pages/OnlineBookingPage';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=user=>act(async()=>root.render(<Popup user={user} onOpen={()=>window.opens++}/>));window.mountUpcoming=user=>act(async()=>root.render(<Upcoming user={user} onClose={()=>window.opens++}/>));window.mountManual=()=>act(async()=>root.render(<Manual services={[{id:'svc',name:'VIP',duration:90,price:350000}]} onClose={()=>window.opens++} onSaved={()=>window.saved++}/>));window.mountPage=user=>act(async()=>root.render(<Page user={user}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader:'jsx' },
  bundle:true, write:false, format:'iife', jsx:'automatic', loader:{'.css':'empty'},
  plugins:[{name:'mock-api',setup(b){
    b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}))
    b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:`export const veraApi={liveTourCollection:async(panel,params)=>{window.lookup=params.search;return {data:{customers:[{id:'c1',name:'Khách Mẫu',phone:'0900000001'}]}}},createOnlineBooking:async body=>{window.sent.push(body);if(window.fail)throw Error('Mất kết nối');return {ok:true}},updateOnlineBooking:async(id,body)=>{if(window.fail)throw Error('Xung đột cập nhật');window.updated={id,...body};window.rows=[];return {ok:true}},onlineBookings:async params=>{window.lastParams=params;return {rows:window.rows,total:window.rows.length}},onlineBookingsUnread:async()=>{window.reads++;return {rows:window.rows}},onlineBookingSeen:async id=>{if(window.fail)throw Error('Mất kết nối');window.seen.push(id)}};`}))
  }}],
})
async function mount(role='letan') {
  const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true})
  const w=dom.window
  w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
  w.IS_REACT_ACT_ENVIRONMENT=true;w.opens=0;w.saved=0;w.sent=[];w.reads=0;w.seen=[]
  w.rows=[{id:1,kind:'booking',customer_name:'<script>Test</script>',phone:'0900000000',appointment_date:'2026-09-30',appointment_time:'14:30',service:'VIP',guests:2,message:'Phòng yên tĩnh\nCảm ơn',status:'new',note:'',revision:0}]
  w.eval(built.outputFiles[0].text);await w.mount({id:'a',role});return dom
}
test('popup shows all booking fields safely, persists acknowledgement and opens inbox',async()=>{
  const dom=await mount(),w=dom.window
  try {
    const text=w.document.body.textContent
    for(const value of ['<script>Test</script>','0900000000','30-09-2026','14:30','VIP','2','Phòng yên tĩnh']) assert.ok(text.includes(value))
    assert.equal(w.document.querySelector('script'),null)
    w.fail=true
    await w.act(async()=>[...w.document.querySelectorAll('button')].find(b=>b.textContent==='Đã xem').click())
    assert.ok(w.document.querySelector('[role="alert"]'));assert.ok(w.document.querySelector('aside'))
    w.fail=false
    await w.act(async()=>[...w.document.querySelectorAll('button')].find(b=>b.textContent==='Mở Booking online').click())
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


test('hide/show keeps request unread; dragging and keyboard movement stay reachable; close acknowledges',async()=>{
  const dom=await mount(),w=dom.window
  try {
    const button=text=>[...w.document.querySelectorAll('button')].find(b=>b.textContent===text)
    await w.act(async()=>button('Ẩn').click())
    assert.equal(w.document.querySelector('dl'),null);assert.equal(w.seen.length,0)
    await w.act(async()=>button('Hiện').click())
    assert.ok(w.document.querySelector('dl'));assert.equal(w.seen.length,0)
    const panel=w.document.querySelector('aside'),handle=w.document.querySelector('.online-booking-drag-handle')
    panel.getBoundingClientRect=()=>({left:100,top:100,width:420,height:300})
    handle.setPointerCapture=()=>{}
    await w.act(async()=>{
      handle.dispatchEvent(new w.MouseEvent('pointerdown',{bubbles:true,button:0,clientX:110,clientY:110}))
      handle.dispatchEvent(new w.MouseEvent('pointermove',{bubbles:true,clientX:160,clientY:180}))
      handle.dispatchEvent(new w.MouseEvent('pointerup',{bubbles:true}))
    })
    assert.equal(panel.style.left,'150px');assert.equal(panel.style.top,'170px')
    await w.act(async()=>handle.dispatchEvent(new w.KeyboardEvent('keydown',{key:'ArrowRight',bubbles:true})))
    assert.equal(panel.style.left,'110px')
    await w.act(async()=>button('Đóng').click())
    assert.equal(w.seen[0],1);assert.equal(w.document.querySelector('aside'),null)
  } finally {await w.unmount();w.close()}
})
test('online booking history has a message column and preserves multiline text',async()=>{
  const dom=await mount(),w=dom.window
  try {
    await w.mountPage({id:'a',role:'letan'})
    assert.ok([...w.document.querySelectorAll('th')].some(th=>th.textContent==='Lời nhắn'))
    assert.equal(w.document.querySelector('td.online-booking-message').textContent,'Phòng yên tĩnh\nCảm ơn')
  } finally {await w.unmount();w.close()}
})

test('date presets reach API; details opens accessible modal and Escape closes it',async()=>{
 const dom=await mount(),w=dom.window
 try {
  await w.mountPage({id:'a',role:'letan'})
  const button=text=>[...w.document.querySelectorAll('button')].find(b=>b.textContent===text)
  await w.act(async()=>button('Ngày mai').click())
  assert.match(w.lastParams.date_from,/^\d{4}-\d{2}-\d{2}$/)
  assert.equal(w.lastParams.date_from,w.lastParams.date_to)
  assert.equal(w.document.querySelectorAll('tbody td[data-label]').length,10)
  await w.act(async()=>button('Chi tiết').click())
  const modal=w.document.querySelector('[role="dialog"]')
  assert.ok(modal);assert.ok(modal.textContent.includes('Đặt lịch'))
  assert.ok(modal.textContent.includes('Phòng yên tĩnh'))
  await w.act(async()=>modal.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true})))
  assert.equal(w.document.querySelector('[role="dialog"]'),null)
 }finally{await w.unmount();w.close()}
})

for (const role of ['admin','quanly','letan']) test(`upcoming ${role}: filter, details, revision update and return`,async()=>{
 const dom=await mount(role),w=dom.window
 try {
  await w.mountUpcoming({role})
  assert.equal(w.lastParams.upcoming,true)
  const button=text=>[...w.document.querySelectorAll('button')].find(b=>b.textContent===text)
  await w.act(async()=>button('Chi tiết').click())
  assert.equal(w.document.querySelectorAll('[role="dialog"]').length,1)
  const select=w.document.querySelector('select')
  await w.act(async()=>{select.value='handled';select.dispatchEvent(new w.Event('change',{bubbles:true}))})
  w.fail=true
  await w.act(async()=>button('Lưu').click())
  assert.ok(w.document.querySelector('[role="alert"]').textContent.includes('Xung đột'))
  assert.equal(w.document.querySelector('select').value,'handled')
  w.fail=false
  await w.act(async()=>button('Lưu').click())
  assert.equal(w.updated.revision,0);assert.equal(w.updated.status,'handled')
  assert.equal(w.document.querySelectorAll('[role="dialog"]').length,1)
  assert.ok(w.document.body.textContent.includes('Không có booking online sắp tới'))
 }finally{await w.unmount();w.close()}
})
test('upcoming does not load or render for other roles',async()=>{
 const dom=await mount('nhanvien'),w=dom.window
 try {
  await w.mountUpcoming({role:'nhanvien'})
  assert.equal(w.lastParams,undefined)
  assert.equal(w.document.querySelector('[role="dialog"]'),null)
 }finally{await w.unmount();w.close()}
})

test('manual booking searches customer phone, fills both fields, retries with same id',async()=>{
 const dom=await mount(),w=dom.window
 try {
  await w.mountManual()
  const change=async(input,value)=>w.act(async()=>{
   const proto=input.tagName==='SELECT'?w.HTMLSelectElement.prototype:w.HTMLInputElement.prototype
   Object.getOwnPropertyDescriptor(proto,'value').set.call(input,value)
   input.dispatchEvent(new w.Event(input.tagName==='SELECT'?'change':'input',{bubbles:true}))
  })
  const phone=w.document.querySelector('input[placeholder="Nhập số điện thoại"]')
  await change(phone,'0900')
  await w.act(async()=>new Promise(resolve=>setTimeout(resolve,300)))
  assert.equal(w.lookup,'0900')
  const option=[...w.document.querySelectorAll('[role="option"]')].find(el=>el.textContent.includes('Khách Mẫu'))
  assert.ok(option)
  await w.act(async()=>option.click())
  assert.equal(phone.value,'0900000001')
  assert.equal(w.document.querySelector('input[placeholder="Nhập tên khách hàng"]').value,'Khách Mẫu')
  const service=w.document.querySelector('select')
  await change(service,service.options[1].value)
  await change(w.document.querySelector('input[type="time"]'),'14:00')
  const submit=()=>w.act(async()=>w.document.querySelector('form').dispatchEvent(new w.Event('submit',{bubbles:true,cancelable:true})))
  w.fail=true;await submit()
  assert.ok(w.document.querySelector('[role="alert"]'))
  w.fail=false;await submit()
  assert.equal(w.saved,1)
  assert.equal(w.sent[0].event_id,w.sent[1].event_id)
  assert.equal(w.sent[1].customer_name,'Khách Mẫu')
  assert.equal(w.sent[1].phone,'0900000001')
 }finally{await w.unmount();w.close()}
})
