import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const bundle = await build({stdin:{contents:`export {default as Toolbar} from './src/components/UiToolbar';export {default as Search} from './src/components/LiveTourSearchSelect';export {publishCustomization} from './src/lib/uiCustomizationStore'`,resolveDir:new URL('..',import.meta.url).pathname},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime'],loader:{'.css':'empty'}})
test('labeled fields retain identity and business callbacks across toolbar relocation',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://test.invalid',pretendToBeVisual:true})
 const names=['window','document','navigator','getComputedStyle','IS_REACT_ACT_ENVIRONMENT']
 const saved=Object.fromEntries(names.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const k of names)Object.defineProperty(globalThis,k,{value:k==='IS_REACT_ACT_ENVIRONMENT'?true:k==='window'?dom.window:dom.window[k],configurable:true})
 const m={exports:{}};new Function('require','module','exports',bundle.outputFiles[0].text)(createRequire(import.meta.url),m,m.exports)
 const {Toolbar,Search,publishCustomization}=m.exports
 const {createRoot}=await import('react-dom/client');const root=createRoot(document.querySelector('#root'))
 let changed='';const render=optional=>React.createElement('form',{},React.createElement(Toolbar,{'data-ui-key':'u-source'}, optional&&React.createElement('label',{},'Optional',React.createElement('input')),React.createElement('label',{},React.createElement('span',{},'Ngày'),React.createElement('input',{'aria-label':'Ngày',onChange:e=>{changed=e.target.value}})),React.createElement(Search,{label:'Nhân viên',value:'',options:[],onChange(){}})),React.createElement(Toolbar,{'data-ui-key':'u-target'}))
 try{
  await act(async()=>root.render(render(false)))
  const date=()=>document.querySelector('[aria-label="Ngày"]').closest('label')
  const key=date().dataset.uiKey
  assert.ok(key.startsWith('l-field-'))
  assert.ok(document.querySelector('.live-tour-search-select').dataset.uiOrigin)
  await act(async()=>root.render(render(true)))
  assert.equal(date().dataset.uiKey,key,'adding an optional field cannot shift saved identities')
  await act(async()=>publishCustomization({[key]:{move_to:'u-target',order:0}},true))
  assert.equal(date().closest('[data-ui-dropzone]').dataset.uiDropzone,'u-target')
  const input=date().querySelector('input')
  await act(()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(input,'test');input.dispatchEvent(new dom.window.Event('input',{bubbles:true}))})
  assert.equal(changed,'test')
  await act(async()=>publishCustomization({},false))
  assert.equal(date().closest('[data-ui-dropzone]').dataset.uiDropzone,'u-source')
 }finally{await act(()=>root.unmount());dom.window.close();for(const [k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}}
})
