import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act, Suspense } from 'react'
import { JSDOM } from 'jsdom'
const require=createRequire(import.meta.url)
const built=await build({stdin:{contents:"export {default as Boundary} from './src/components/PageErrorBoundary';export {recoverablePage} from './src/lib/recoverablePage'",resolveDir:process.cwd()},bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react/jsx-runtime']})

test('failed page import preserves menu and retries the rejected lazy module without reloading',async()=>{
  const dom=new JSDOM('<body><div id="root"></div></body>',{url:'https://example.test'})
  const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true}
  const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
  for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true})
  const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports)
  const {Boundary,recoverablePage}=mod.exports
  let attempts=0,fail=true
  const Page=recoverablePage(async()=>{attempts++;if(fail)throw Error('Failed to fetch dynamically imported module');return {default:()=>React.createElement('form',null,'Leave form')}})
  const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
  const originalError=console.error
  console.error=()=>{}
  window.addEventListener('error',event=>event.preventDefault())
  const render=page=>act(async()=>root.render(React.createElement(React.Fragment,null,React.createElement('nav',null,'Menu'),React.createElement(Boundary,{key:page,page,onRetry:Page.reset},React.createElement(Suspense,{fallback:'Loading'},React.createElement(Page))))))
  try{
    await render('leave')
    assert.match(document.querySelector('[role="alert"]').textContent,/Không mở được Đăng ký nghỉ/)
    assert.equal(document.querySelector('nav').textContent,'Menu')
    assert.equal(attempts,1)
    await act(async()=>document.querySelector('button').click())
    assert.equal(attempts,2);assert.ok(document.querySelector('[role="alert"]'))
    fail=false
    await act(async()=>document.querySelector('button').click())
    assert.equal(attempts,3);assert.equal(document.querySelector('form').textContent,'Leave form')
    assert.equal(document.querySelector('[role="alert"]'),null)
    await render('schedule')
    assert.equal(attempts,3)
    assert.equal(window.location.href,'https://example.test/')
  }finally{
    await act(async()=>root.unmount());dom.window.close();console.error=originalError
    for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}
  }
})
