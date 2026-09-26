import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const built=await build({stdin:{contents:"export {default} from './src/components/PaymentCustomerScreen'",resolveDir:fileURLToPath(new URL('..',import.meta.url)),loader:'jsx'},bundle:true,write:false,loader:{'.css':'empty'},platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime','react-dom']})
test('Customer QR updates safely, handles blocked popup and closes stale screen',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://test.invalid',pretendToBeVisual:true})
 const saved=Object.fromEntries(['window','document','navigator','IS_REACT_ACT_ENVIRONMENT'].map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
 for(const key of ['window','document','navigator'])Object.defineProperty(globalThis,key,{value:key==='window'?dom.window:dom.window[key],configurable:true})
 globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
 const Screen=module.exports.default,{createRoot}=await import('react-dom/client'),root=createRoot(document.querySelector('#root'))
 let closed=false
 const child=new JSDOM('<body></body>',{url:'https://test.invalid'})
 const popup={document:child.window.document,focus(){},close(){closed=true},closed:false}
 const props={bank:{enabled:true,bank_id:'VCB',account_no:'123456789',account_name:'<script>bad</script>'},amount:270000,reference:'VERA-123',settings:{enabled:true,width:420,height:600,qr_size:300}}
 try{
  window.open=()=>null
  await act(()=>root.render(React.createElement(Screen,props)))
  await act(()=>document.querySelector('button').click())
  assert.match(document.querySelector('[role=alert]').textContent,/chặn cửa sổ/)
  window.open=()=>popup
  await act(()=>document.querySelector('button').click())
  assert.match(popup.document.body.textContent,/270\.000/)
  assert.equal(popup.document.querySelector('script'),null)
  assert.equal(new URL(popup.document.querySelector('img').src).searchParams.get('amount'),'270000')
  await act(()=>root.render(React.createElement(Screen,{...props,amount:180000})))
  assert.equal(new URL(popup.document.querySelector('img').src).searchParams.get('amount'),'180000')
  await act(()=>root.render(React.createElement(Screen,{...props,settings:{enabled:false}})))
  assert.equal(closed,true)
  assert.equal(document.querySelector('button'),null)
 }finally{await act(()=>root.unmount());child.window.close();dom.window.close();for(const [key,descriptor]of Object.entries(saved)){if(descriptor)Object.defineProperty(globalThis,key,descriptor);else delete globalThis[key]}}
})
