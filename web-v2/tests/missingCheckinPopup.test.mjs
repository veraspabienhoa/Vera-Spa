import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { readFileSync } from 'node:fs'
const built = await build({stdin:{contents:`import React from 'react'; import {createRoot} from 'react-dom/client'; import Popup from './src/components/MissingCheckinPopup'; const root=createRoot(document.getElementById('root')); window.mount=user=>root.render(<Popup user={user}/>); window.unmount=()=>root.unmount();`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'feed',setup(b){
 b.onResolve({filter:/\/lib\/notificationFeed$/},()=>({path:'feed',namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const subscribeNotificationFeed=fn=>{window.receive=fn; window.subscriptions++;return()=>{window.receive=null;window.stops++}};'}))
}}]})
const tick=()=>new Promise(resolve=>setTimeout(resolve,35))
const row=(employee='worker')=>({employee,tag:`missing-${employee}`,body:`${employee} chưa check-in`,expires_at:new Date(Date.now()+60_000).toISOString()})
async function mount(role){const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});const w=dom.window;w.subscriptions=0;w.stops=0;w.eval(built.outputFiles[0].text);w.mount({role,employee_username:'viewer'});await tick();return dom}
const publish=async(w,rows,config={})=>{w.receive({missing_checkins:rows,settings:[{key:'missing_checkin',...config}]});await tick()}
for(const role of ['admin','letan','quanly']) test(`${role}: current absence opens, deduplicates, dismisses and clears on check-in`,async()=>{
 const dom=await mount(role),w=dom.window
 try {
  await publish(w,[row()]);assert.equal(w.document.querySelectorAll('.missing-checkin-popup li').length,1)
  await publish(w,[row()]);assert.equal(w.document.querySelectorAll('.missing-checkin-popup li').length,1)
  w.document.querySelector('button').click();await tick();await publish(w,[row()]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[row(),row('new-worker')]);assert.equal(w.document.querySelectorAll('li').length,1)
  assert.equal(w.document.querySelector('li strong').textContent,'new-worker')
  await publish(w,[]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  assert.equal(w.subscriptions,1)
 } finally {w.unmount();w.close()}
})
for(const role of ['nhanvien','leader','giamdoc','']) test(`${role || 'anonymous'} does not subscribe or show manager absence details`,async()=>{
 const dom=await mount(role);assert.equal(dom.window.subscriptions,0);assert.equal(dom.window.document.querySelector('.missing-checkin-popup'),null);dom.window.unmount();dom.window.close()
})
test('disabled, expired and failed-refresh snapshots cannot leave an old absence popup visible',async()=>{
 const dom=await mount('admin'),w=dom.window
 try {
  await publish(w,[row()],{channel_enabled:{popup:false}});assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[{...row(),expires_at:new Date(Date.now()-1).toISOString()}]);assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  await publish(w,[row()]);assert.ok(Boolean(w.document.querySelector('.missing-checkin-popup')))
  const originalNow=w.Date.now;w.Date.now=()=>originalNow()+61_000
  w.document.dispatchEvent(new w.Event('visibilitychange'));await tick();assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  w.Date.now=originalNow
  await publish(w,[row()]);w.dispatchEvent(new w.CustomEvent('vera-notification-settings-changed',{detail:{key:'missing_checkin',enabled:false}}));await tick();assert.equal(w.document.querySelector('.missing-checkin-popup'),null)
  w.mount({role:'admin',employee_username:'viewer',must_change_password:true});await tick();assert.equal(w.receive,null)
 }finally{w.unmount();w.close()}
})
test('manager popup is mounted outside the Live Tour notification suppression',()=>{
 const source=readFileSync('src/components/AppShell.jsx','utf8')
 assert.ok(source.includes('<MissingCheckinPopup key='))
 assert.equal(/showPageNotifications\s*&&\s*<MissingCheckinPopup/.test(source),false)
})
