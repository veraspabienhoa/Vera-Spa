import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const built=await build({stdin:{contents:"export {default as Custom} from './src/components/LayoutCustomElements'; export {default as Toolbar} from './src/components/UiToolbar'; export {default as Text} from './src/components/UiCustomText'; export {publishCustomization} from './src/lib/uiCustomizationStore'",resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'jsx'},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime']})
test('Labels preserve business handler; toolbar sorts actual DOM, groups safely, restores defaults and forwards refs',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{pretendToBeVisual:true})
 const saved=Object.fromEntries(['window','document','navigator','MutationObserver','IS_REACT_ACT_ENVIRONMENT'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const key of ['window','document','navigator','MutationObserver'])Object.defineProperty(globalThis,key,{value:key==='window'?dom.window:dom.window[key],configurable:true})
 globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
 const {Toolbar,Text,Custom,publishCustomization}=module.exports
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.querySelector('#root')),ref=React.createRef()
 let count=0
 const buttons=['a','b','c','d'].map(key=>React.createElement('button',{'data-ui-key':'u-'+key,key,onClick:()=>count++},React.createElement(Text,{uiKey:'u-'+key},key)))
 try{
  await act(()=>root.render(React.createElement(Toolbar,{'data-ui-key':'u-group',ref},buttons)))
  assert.equal(ref.current.tagName,'DIV')
  await act(()=>publishCustomization({'u-a':{label:'Tên mới',order:3},'u-b':{order:0}}))
  assert.equal(document.querySelector('button').textContent,'b')
  await act(()=>document.querySelector('[data-ui-key="u-a"]').click())
  assert.equal(count,1)
  assert.equal(document.querySelector('[data-ui-key="u-a"]').textContent,'Tên mới')
  await act(()=>publishCustomization({'u-group':{mode:'group'}}))
  assert.equal(document.querySelectorAll('details button').length,2)
  document.querySelector('details').open=true
  await act(()=>document.dispatchEvent(new window.KeyboardEvent('keydown',{key:'Escape',bubbles:true})))
  assert.equal(document.querySelector('details').open,false)
  await act(()=>publishCustomization({}))
  assert.equal(document.querySelector('details'),null)
  assert.equal(document.querySelector('button').textContent,'a')
  const screen=(showTarget=true,showAction=true)=>React.createElement('main',null,
    React.createElement(Toolbar,{'data-ui-key':'u-source'},showAction ? buttons : buttons.slice(1)),
    showTarget && React.createElement(Toolbar,{'data-ui-key':'u-target'},React.createElement('button',{'data-ui-key':'u-other'},'Other')))
  await act(()=>root.render(screen()))
  await act(()=>publishCustomization({'u-a':{move_to:'u-target'}}))
  assert.equal(document.querySelector('[data-ui-key="u-a"]').closest('[data-ui-dropzone]').dataset.uiDropzone,'u-target')
  await act(()=>document.querySelector('[data-ui-key="u-a"]').click())
  assert.equal(count,2,'moving preserves the action handler')
  await act(()=>root.render(screen(true,false)))
  assert.equal(document.querySelector('[data-ui-key="u-a"]'),null,'hidden actions are not resurrected by saved layout')
  await act(()=>root.render(screen(false)))
  assert.equal(document.querySelector('[data-ui-key="u-a"]').closest('[data-ui-dropzone]').dataset.uiDropzone,'u-source','missing target falls back')
  await act(()=>root.render(screen()))
  await act(()=>publishCustomization({}))
  assert.equal(document.querySelector('[data-ui-key="u-a"]').closest('[data-ui-dropzone]').dataset.uiDropzone,'u-source','restore default')
  const nested={'l-custom-frame':{custom_kind:'frame',custom_page:'settings',custom_anchor:'u-b'},'u-a':{move_to:'l-custom-frame'}}
  await act(async()=>root.render(React.createElement('div',{className:'app-shell'},React.createElement(Toolbar,{'data-ui-key':'u-source'},buttons),React.createElement(Custom,{items:nested,page:'settings',editing:false}))))
  await act(async()=>publishCustomization(nested))
  assert.equal(document.querySelector('[data-ui-key="u-a"]').closest('[data-ui-dropzone]').dataset.uiDropzone,'l-custom-frame','native action portals into a custom frame inside its original toolbar')
  await act(async()=>document.querySelector('[data-ui-key="u-a"]').click())
  assert.equal(count,3)
  await act(async()=>root.render(React.createElement('div',{className:'app-shell'},React.createElement(Toolbar,{'data-ui-key':'u-source'},buttons),React.createElement(Custom,{items:{},page:'settings',editing:false}))))
  await act(async()=>publishCustomization({}))
  assert.equal(document.querySelector('[data-ui-key="u-a"]').closest('[data-ui-dropzone]').dataset.uiDropzone,'u-source')
 }finally{await act(()=>root.unmount());dom.window.close();for(const [key,value] of Object.entries(saved)){if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}}
})
