import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const built=await build({entryPoints:[fileURLToPath(new URL('../src/pages/NotificationSettingsPage.jsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime'],loader:{'.css':'empty'},plugins:[{name:'fixture',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const veraApi=globalThis.__notificationApi',loader:'js'}))}}]})
test('Admin searches tasks, selects multiple recipients/channels and persists global ordering',async()=>{
 const dom=new JSDOM('<body><div id="root"></div></body>',{url:'https://test.invalid',pretendToBeVisual:true})
 const names=['window','document','navigator','CustomEvent','IS_REACT_ACT_ENVIRONMENT','__notificationApi']
 const previous=Object.fromEntries(names.map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const key of ['window','document','navigator','CustomEvent'])Object.defineProperty(globalThis,key,{value:key==='window'?dom.window:dom.window[key],configurable:true})
 globalThis.IS_REACT_ACT_ENVIRONMENT=true
 let server={revision:0,settings:[{key:'birthday',label:'Sinh nhật',description:'Nhắc sinh nhật',enabled:true},{key:'leave',label:'Nghỉ phép',description:'Nghỉ phép',enabled:true}],recipients:[{id:'a',name:'An',username:'an',role:'nhanvien'},{id:'b',name:'Bình',username:'binh',role:'letan'}],channels:[{key:'in_app',label:'Trong ứng dụng'},{key:'push',label:'Thông báo đẩy'}]}
 const writes=[]
 let failSave=false
 globalThis.__notificationApi={notificationSettings:async()=>structuredClone(server),notificationTasks:async()=>({tasks:[{key:'task-1',label:'Live Tour · Thanh toán',group:'Live Tour',description:'checkout'},{key:'task-2',label:'Đào tạo',group:'Đào tạo',description:'training'}]}),createNotification:async body=>{writes.push(body);server={...server,revision:1,settings:[...server.settings,{...body,key:'custom',custom:true,routed:true}]};return structuredClone(server)},updateNotificationSetting:async(key,body)=>{if(failSave)throw Error('Thử lại khi mạng ổn định');writes.push(body);server={...server,revision:server.revision+1,settings:server.settings.map(item=>item.key===key?{...item,...body,routed:true}:item)};return structuredClone(server)},orderNotifications:async body=>{writes.push(body);server={...server,revision:2,settings:body.keys.map(key=>server.settings.find(item=>item.key===key))};return structuredClone(server)}}
 const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
 const {createRoot}=await import('react-dom/client');const root=createRoot(document.querySelector('#root'))
 const click=async label=>act(async()=>[...document.querySelectorAll('button')].find(node=>node.textContent.includes(label)).click())
 const set=async(node,value)=>act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event('input',{bubbles:true}))})
 try{
  await act(async()=>root.render(React.createElement(module.exports.default,{user:{role:'admin'}})))
  await click('Tạo thông báo')
  assert.ok(document.querySelector('dialog[aria-modal="true"][open]'))
  assert.equal(document.body.style.overflow,'hidden')
  await set(document.querySelector('[aria-label="Tìm tác vụ"]'),'thanh toan')
  const select=document.querySelector('[aria-label="Tác vụ kích hoạt"]');assert.equal(select.options.length,2)
  await act(async()=>{select.value='task-1';select.dispatchEvent(new window.Event('change',{bubbles:true}))})
  const people=[...document.querySelectorAll('.notification-recipient-list input')]
  for(const person of people)await act(async()=>person.click())
  await act(async()=>document.querySelectorAll('.notification-channel input')[1].click())
  await click('Lưu thông báo')
  assert.deepEqual(writes[0].recipients,['a','b']);assert.deepEqual(writes[0].channels,['in_app','push']);assert.equal(writes[0].source_key,'task-1')
  await act(async()=>document.querySelector('[aria-label="Đưa Live Tour · Thanh toán lên"]').click())
  assert.deepEqual(writes[1].keys,['birthday','custom','leave']);assert.equal(writes[1].revision,1)
  const editButton=document.querySelector('.notification-card-actions button:last-child')
  await act(async()=>{editButton.focus();editButton.click()})
  const groups=()=>[...document.querySelectorAll('.notification-recipient-groups label')]
  assert.deepEqual(groups().map(el=>el.textContent),['Nhân viên','Lễ tân','Người theo dõi','Quản lý','Giám đốc','Tất cả tài khoản','Admin'])
  assert.equal(groups()[2].querySelector('input').disabled,true)
  await act(async()=>groups()[0].querySelector('input').click())
  assert.equal(document.querySelector('.notification-recipient-list input').checked,true)
  assert.equal(document.querySelector('.notification-recipient-list input').disabled,true)
  failSave=true
  await click('Lưu thông báo')
  assert.match(document.querySelector('dialog [role="alert"]').textContent,/Thử lại/)
  assert.equal(groups()[0].querySelector('input').checked,true,'save failure preserves group choice')
  failSave=false
  await click('Lưu thông báo')
  assert.deepEqual(writes.at(-1).recipients,['group:nhanvien'])
  assert.equal(document.querySelector('dialog'),null)
  assert.equal(document.body.style.overflow,'')
  assert.equal(document.activeElement,editButton)
  await act(async()=>editButton.click())
  assert.equal(groups()[0].querySelector('input').checked,true,'saved groups reopen checked')
  const beforeCancel=writes.length
  await act(async()=>document.querySelector('dialog').dispatchEvent(new window.Event('cancel',{cancelable:true})))
  assert.equal(document.querySelector('dialog'),null)
  assert.equal(writes.length,beforeCancel)
  await act(async()=>root.render(React.createElement(module.exports.default,{user:{role:'letan'}})))
  assert.equal([...document.querySelectorAll('button')].find(node=>node.textContent.includes('Tạo thông báo')),undefined)
 }finally{await act(async()=>root.unmount());dom.window.close();for(const [key,value]of Object.entries(previous)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}}
})
