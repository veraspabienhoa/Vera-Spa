import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
Object.defineProperties(globalThis, {
  window: { value: dom.window, configurable: true }, document: { value: dom.window.document, configurable: true },
  navigator: { value: dom.window.navigator, configurable: true }, IS_REACT_ACT_ENVIRONMENT: { value: true, configurable: true },
})
const { createRoot } = await import('react-dom/client')
const require = createRequire(import.meta.url)
async function component(name) {
  const built = await build({ entryPoints: [fileURLToPath(new URL(`../src/components/${name}.jsx`, import.meta.url))],
    bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
    external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' } })
  const module = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(require, module, module.exports)
  return module.exports.default
}
const BookingDialog = await component('LiveTourBookingDialog')
async function render(Component) {
  const root = createRoot(document.querySelector('#root'))
  await act(() => root.render(React.createElement(Component)))
  return async () => act(() => root.unmount())
}


test('add-on picker requires another idle worker, submits and reopens saved pair', async () => {
  const services = [{ id:'main', name:'90 PR Tiêu chuẩn', duration:90, price:300000 }, { id:'extra', name:'Thêm 1 KTV', duration:30, price:100000 }]
  const main = {id:'e1', name:'Ngọc Hân', shift:'Ca 1', work_status:'Đi làm', service:'90 PR Tiêu chuẩn', status:'Đang chờ', room:'20.1', service_items:[{service_id:'main',quantity:1}]}
  const idle = {id:'e2',name:'KTV thêm',shift:'Ca 1',work_status:'Đi làm',service:''}
  const busy = {id:'e3',name:'Đang bận',shift:'Ca 1',work_status:'Đi làm',service:'90 PR Tiêu chuẩn',status:'Đang chờ'}
  const calls = []
  const data = { revision:7, services, state:{employees:[main,idle,busy],rooms:[{id:'room',name:'20.1'}]} }
  const props = {data, context:{employeeId:'e1'},canBook:true,canOperate:true,onClose(){}, onAction:async(...args)=>{calls.push(args);return {}}}
  let dispose = await render(() => React.createElement(BookingDialog,props))
  try {
    assert.ok(!document.body.textContent.includes('KTV thêm *'))
    const serviceLabel=[...document.querySelectorAll('label')].find(node=>node.textContent==='Dịch vụ')
    await act(()=>document.getElementById(serviceLabel.htmlFor).focus())
    await act(()=>[...document.querySelectorAll('[role="option"]')].find(node=>node.textContent.includes('Thêm 1 KTV')).click())
    await act(()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})))
    assert.equal(calls.length,0)
    const label=[...document.querySelectorAll('label')].find(node=>node.textContent==='KTV thêm *')
    await act(()=>document.getElementById(label.htmlFor).focus())
    const options=[...document.querySelectorAll('[role="option"]')]
    assert.equal(options.length,1)
    assert.match(options[0].textContent,/KTV thêm/)
    await act(()=>options[0].click())
    await act(()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})))
    assert.equal(calls.length,1)
    assert.equal(calls[0][1].additional_ktv_id,'e2')
    assert.equal(calls[0][1].service_items.length,2)
    assert.ok(document.body.textContent.includes('400.000 đ'))
  } finally { await dispose() }
  Object.assign(main,{additional_ktv_id:'e2',additional_ktv_item:{service_id:'extra',quantity:1},paired_booking_id:'pair'})
  Object.assign(idle,{primary_ktv_id:'e1',paired_booking_id:'pair',room:'20.1',service:'Thêm 1 KTV',status:'Đang chờ'})
  data.room_assignments=[main,idle]
  dispose=await render(()=>React.createElement(BookingDialog,props))
  try {
    const label=[...document.querySelectorAll('label')].find(node=>node.textContent==='KTV thêm *')
    assert.equal(document.getElementById(label.htmlFor).value,'KTV thêm')
    assert.ok(!document.body.textContent.includes('đang được sử dụng'))
    assert.ok(document.body.textContent.includes('400.000 đ'))
    await act(()=>document.querySelector('form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})))
    assert.equal(calls.at(-1)[1].additional_ktv_id,'e2')
  } finally { await dispose() }
  dom.window.close()
})
