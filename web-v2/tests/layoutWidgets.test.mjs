import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import {createRequire} from 'node:module'
import {fileURLToPath} from 'node:url'
import React,{act} from 'react'
import {JSDOM} from 'jsdom'
import {removeLayoutItems} from '../src/lib/layoutSelection.js'
import {freeMovePosition} from '../src/lib/layoutFreeMove.js'
const built=await build({entryPoints:[fileURLToPath(new URL('../src/components/LayoutCustomElements.jsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime'],loader:{'.css':'empty'}})
test('nested custom controls filter only their linked table and deleting a parent restores native children',async()=>{
 const dom=new JSDOM('<div class="app-shell"><main class="page-content"></main></div><div id="root"></div>',{pretendToBeVisual:true})
 const keys=['window','document','navigator','MutationObserver','IS_REACT_ACT_ENVIRONMENT'],old=Object.fromEntries(keys.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const k of keys)Object.defineProperty(globalThis,k,{configurable:true,value:k==='IS_REACT_ACT_ENVIRONMENT'?true:k==='window'?dom.window:dom.window[k]})
 const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const {createRoot}=await import('react-dom/client');const root=createRoot(document.querySelector('#root'))
 const item=(custom_kind,extra={})=>({custom_kind,custom_page:'settings',...extra})
 const config={
  'l-custom-frame':item('frame'),
  'l-custom-row':item('row',{move_to:'l-custom-frame'}),
  'l-custom-table':item('table',{move_to:'l-custom-frame',custom_text:'Tên | Loại | Ngày\nAn | A | 23-09-2026\nBình | B | 24-09-2026'}),
  'l-custom-search':item('search',{move_to:'l-custom-row',custom_target:'l-custom-table',custom_text:'Tìm dữ liệu'}),
  'l-custom-dropdown':item('dropdown',{move_to:'l-custom-row',custom_target:'l-custom-table',custom_options:'A\nB'}),
  'l-custom-date':item('date',{move_to:'l-custom-row',custom_target:'l-custom-table'}),
  'l-custom-filter':item('filter',{move_to:'l-custom-row',custom_target:'l-custom-table',custom_text:'Lọc'}),
 }
 try{
  await act(async()=>root.render(React.createElement(mod.exports.default,{items:config,page:'settings',editing:false})))
  assert.ok(document.querySelector('.layout-custom-frame .layout-custom-row input[type=search]'))
  assert.equal(document.querySelectorAll('.layout-custom-table tbody tr').length,2)
  const search=document.querySelector('input[type=search]')
  await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(search,'An');search.dispatchEvent(new window.Event('input',{bubbles:true}))})
  assert.equal(document.querySelectorAll('.layout-custom-table tbody tr').length,2,'filter button applies the staged values')
  await act(async()=>document.querySelector('.layout-custom-filter button').click())
  assert.equal(document.querySelectorAll('.layout-custom-table tbody tr').length,1)
  assert.match(document.querySelector('.layout-custom-table tbody').textContent,/An/)
  assert.equal(document.querySelector('.layout-custom-date input[type=text]').placeholder,'dd-mm-yyyy')
  const next=removeLayoutItems({...config,'u-native':{move_to:'l-custom-row',width:150}},['l-custom-frame'])
  assert.deepEqual(next,{'u-native':{width:150}})
  await act(async()=>root.render(React.createElement(mod.exports.default,{items:next,page:'settings',editing:false})))
  assert.equal(document.querySelector('.layout-custom-frame'),null)
 }finally{await act(async()=>root.unmount());dom.window.close();for(const [k,v]of Object.entries(old)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}}
})
test('drag snaps edges and centers with an Alt bypass',()=>{
 const start={rect:{left:100,top:100,width:40,height:20},original:{},scrollX:0,scrollY:0,targets:[{left:200,right:300,top:200,bottom:300}]}
 assert.equal(freeMovePosition(start,57,80,1000,true).x,60,'right edge snaps to left edge')
 assert.equal(freeMovePosition(start,57,80,1000,false).x,57)
 assert.equal(freeMovePosition(start,127,139,1000,true).guides.x,250,'center snaps to center')
 assert.equal(freeMovePosition(start,127,139,1000,true).guides.y,250)
})
