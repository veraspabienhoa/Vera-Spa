import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { readLayoutMetrics, resizeDimensions } from '../src/lib/layoutMetrics.js'
import { layoutCandidates } from '../src/lib/sharedLayout.js'
const built=await build({entryPoints:[fileURLToPath(new URL('../src/components/LayoutResizeOverlay.jsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime','react-dom']})
test('Resize overlay supports native controls without moving their DOM; cancel and keyboard work',async()=>{
 const dom=new JSDOM('<div id="root"></div><header style="font-size:18px;color:rgb(20,60,40)"><input id="target" value="unchanged"/><select><option>Option</option></select><span class="vera-date-input"></span></header>',{pretendToBeVisual:true})
 const names=['window','document','navigator','getComputedStyle','IS_REACT_ACT_ENVIRONMENT'],before=Object.fromEntries(names.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const k of ['window','document','navigator','getComputedStyle'])Object.defineProperty(globalThis,k,{value:k==='window'?dom.window:dom.window[k],configurable:true})
 globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.querySelector('#root')),target=document.querySelector('#target'),parent=target.parentElement
 target.getBoundingClientRect=()=>({left:10,top:10,width:120,height:40});parent.getBoundingClientRect=()=>({left:0,top:0,width:300,height:80});Object.defineProperty(parent,'clientWidth',{value:300})
 const events=[]
 try{
  for(const el of [parent,target,document.querySelector('select'),document.querySelector('.vera-date-input')])assert.ok(el.matches(layoutCandidates))
  assert.equal(readLayoutMetrics(parent).appearance.font_size,18)
  assert.equal(readLayoutMetrics(parent).appearance.normal.text,'#143c28')
  await act(async()=>{root.render(React.createElement(module.exports.default,{selected:target,onResize:(size,phase)=>events.push({size,phase}),onMetrics(){}}));})
  await act(()=>new Promise(r=>setTimeout(r,30)))
  const handle=document.querySelector('[aria-label="Kéo góc để đổi kích thước"]');assert.ok(handle)
  await act(()=>handle.dispatchEvent(new window.MouseEvent('pointerdown',{bubbles:true,clientX:10,clientY:10})))
  await act(()=>handle.dispatchEvent(new window.MouseEvent('pointermove',{bubbles:true,clientX:80,clientY:40})))
  assert.deepEqual(events.at(-1),{size:{width:190,height:70},phase:'move'})
  await act(()=>handle.dispatchEvent(new window.KeyboardEvent('keydown',{bubbles:true,key:'Escape'})))
  assert.equal(events.at(-1).phase,'cancel')
  await act(()=>handle.dispatchEvent(new window.KeyboardEvent('keydown',{bubbles:true,key:'ArrowRight',shiftKey:true})))
  assert.deepEqual(events.at(-1),{size:{width:130,height:40},phase:'keyboard'})
  assert.equal(target.parentElement,parent);assert.equal(target.value,'unchanged');assert.equal(target.children.length,0)
  assert.deepEqual(resizeDimensions(120,40,5000,-100,300),{width:300,height:24})
 }finally{await act(()=>root.unmount());dom.window.close();for(const [k,v]of Object.entries(before)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}}
})
