import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { readFileSync } from 'node:fs'
const built = await build({stdin:{contents:`import React, {act} from 'react'; import {createRoot} from 'react-dom/client'; import Popup from './src/components/MissingCheckinPopup'; const root=createRoot(document.getElementById('root')); window.act=act;window.mount=user=>act(async()=>root.render(<Popup user={user}/>)); window.unmount=()=>act(async()=>root.unmount());`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'feed',setup(b){
 b.onResolve({filter:/\/lib\/notificationFeed$/},()=>({path:'feed',namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const subscribeNotificationFeed=fn=>{window.receive=fn; window.subscriptions++;return()=>{window.receive=null;window.stops++}};'}))
}}]})
const row=(employee='worker')=>({employee,tag:`missing-${employee}`,body:`${employee} chưa check-in`,expires_at:new Date(Date.now()+60_000).toISOString()})
async function mount(role){const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});const w=dom.window;w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}};w.IS_REACT_ACT_ENVIRONMENT=true;w.subscriptions=0;w.stops=0;w.eval(built.outputFiles[0].text);await w.mount({role,employee_username:'viewer'});return dom}
const publish=async(w,rows,config={})=>{await w.act(async()=>w.receive({missing_checkins:rows,settings:[{key:'missing_checkin',...config}]}))}
for(const role of ['admin','letan','quanly']) test(`${role}: current absence opens, deduplicates, dismisses and clears on check-in`,async()=>{
 const dom=await mount(role),w=dom.window
 try {
  await publish(w,[row()]);assert.equal(w.document.querySelectorAll('.missing-checkin-popup li').length,1)
  await publish(w,[row()]);assert.equal(w.document.querySelectorAll('.missing-checkin-popup li').length,1)
  await w.act(async()=>w.document.querySelector('.missing-checkin-seen').click());await publish(w,[row()]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[row(),row('new-worker')]);assert.equal(w.document.querySelectorAll('li').length,1)
  assert.equal(w.document.querySelector('li strong').textContent,'new-worker')
  await publish(w,[]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  assert.equal(w.subscriptions,1)
 } finally {await w.unmount();w.close()}
})
for(const role of ['nhanvien','leader','giamdoc','']) test(`${role || 'anonymous'} does not subscribe or show manager absence details`,async()=>{
 const dom=await mount(role);assert.equal(dom.window.subscriptions,0);assert.equal(dom.window.document.querySelector('.missing-checkin-popup'),null);await dom.window.unmount();dom.window.close()
})
test('disabled, expired and failed-refresh snapshots cannot leave an old absence popup visible',async()=>{
 const dom=await mount('admin'),w=dom.window
 try {
  await publish(w,[row()],{channel_enabled:{popup:false}});assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[{...row(),expires_at:new Date(Date.now()-1).toISOString()}]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[row()]);assert.ok(Boolean(w.document.querySelector('.missing-checkin-popup')))
  const originalNow=w.Date.now;w.Date.now=()=>originalNow()+61_000
  await w.act(async()=>w.document.dispatchEvent(new w.Event('visibilitychange')));assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  w.Date.now=originalNow
  await publish(w,[row()]);await w.act(async()=>w.dispatchEvent(new w.CustomEvent('vera-notification-settings-changed',{detail:{key:'missing_checkin',enabled:false}})));assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await w.mount({role:'admin',employee_username:'viewer',must_change_password:true});assert.equal(w.receive,null)
 }finally{await w.unmount();w.close()}
})
test('manager popup is mounted outside the Live Tour notification suppression',()=>{
 const source=readFileSync('src/components/AppShell.jsx','utf8')
 assert.ok(source.includes('<MissingCheckinPopup key='))
 assert.equal(/showPageNotifications\s*&&\s*<MissingCheckinPopup/.test(source),false)
})

test('Đã xem survives remount, empty refresh and account changes; new day still alerts',async()=>{
 const dom=await mount('admin'),w=dom.window
 try {
  const today={...row('Test Employee'),tag:'vera-missing-checkin-2026-09-27-testemployee'}
  await publish(w,[today,today]);assert.equal(w.document.querySelectorAll('li').length,1)
  const seen=[...w.document.querySelectorAll('button')].find(button=>button.textContent==='Đã xem')
  assert.ok(seen)
  await w.act(async()=>seen.click())
  assert.deepEqual(JSON.parse(w.localStorage.getItem('vera-missing-checkin-seen:viewer')),[today.tag])
  await publish(w,[]);await publish(w,[today]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await w.mount({role:'letan',employee_username:'other'});await publish(w,[today]);assert.ok(w.document.querySelector('.missing-checkin-popup'))
  await w.mount({role:'admin',employee_username:'viewer'});await publish(w,[today]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[{...today,tag:'vera-missing-checkin-2026-09-28-testemployee'}]);assert.ok(w.document.querySelector('.missing-checkin-popup'))
 }finally{await w.unmount();w.close()}
})

test('seen state synchronizes tabs and tolerates unavailable storage',async()=>{
 const dom=await mount('admin'),w=dom.window
 try {
  await publish(w,[row()]);w.localStorage.setItem('vera-missing-checkin-seen:viewer',JSON.stringify([row().tag]))
  await w.act(async()=>w.dispatchEvent(new w.StorageEvent('storage',{key:'vera-missing-checkin-seen:viewer'})))
  assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[row('new')])
  Object.defineProperty(w,'localStorage',{get(){throw new Error('Storage blocked')}})
  await w.act(async()=>w.document.querySelector('.missing-checkin-seen').click())
  await publish(w,[row('new')]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
 }finally{await w.unmount();w.close()}
})


test('hide/show preserves unread rows and each employee is acknowledged independently',async()=>{
 const dom=await mount('letan'),w=dom.window
 try {
  await publish(w,[row('A'),row('B')])
  const toggle=()=>w.document.querySelector('header button')
  await w.act(async()=>toggle().click())
  assert.equal(toggle().textContent,'Hiện thông báo')
  assert.equal(toggle().getAttribute('aria-expanded'),'false')
  assert.equal(w.document.querySelector('.missing-checkin-popup [hidden]').querySelectorAll('li').length,2)
  assert.equal(w.localStorage.getItem('vera-missing-checkin-seen:viewer'),null)
  await publish(w,[row('A'),row('B'),row('C')])
  assert.match(w.document.querySelector('header strong').textContent,/3/)
  await w.mount({role:'admin',employee_username:'another'})
  await w.mount({role:'letan',employee_username:'viewer'})
  await publish(w,[row('A'),row('B')])
  assert.equal(toggle().textContent,'Hiện thông báo')
  await w.act(async()=>toggle().click())
  assert.equal(toggle().textContent,'Ẩn thông báo')
  await w.act(async()=>w.document.querySelector('li .missing-checkin-seen').click())
  assert.deepEqual([...w.document.querySelectorAll('li strong')].map(el=>el.textContent),['B'])
  await publish(w,[row('A'),row('B')])
  assert.deepEqual([...w.document.querySelectorAll('li strong')].map(el=>el.textContent),['B'])
  assert.deepEqual(JSON.parse(w.localStorage.getItem('vera-missing-checkin-seen:viewer')),['missing-A'])
 }finally{await w.unmount();w.close()}
})
