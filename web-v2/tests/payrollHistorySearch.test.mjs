import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
test('finds a saved payroll by month/year and opens exact view/edit IDs', async t => {
 const dom = new JSDOM('<div id="root"></div>', { url:'https://example.test' })
 const prior = { window:globalThis.window, document:globalThis.document, IS_REACT_ACT_ENVIRONMENT:globalThis.IS_REACT_ACT_ENVIRONMENT }
 globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 const b=await build({stdin:{contents:"export {default} from './src/components/PayrollHistorySearch'",resolveDir:process.cwd()},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'}})
 const mod={exports:{}};new Function('require','module','exports',b.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.querySelector('#root')),actions=[]
 t.after(async()=>{await act(()=>root.unmount());dom.window.close();Object.assign(globalThis,prior)})
 const items=[{id:'exact/sep',label:'Kỳ 2 - Tháng 9/2026'},{id:'other',label:'Kỳ 1 - Tháng 8/2026'}]
 const props={items,onView:id=>actions.push(['view',id]),onEdit:id=>actions.push(['edit',id])}
 await act(()=>root.render(React.createElement(mod.exports.default,props)))
 assert.equal(document.querySelectorAll('article').length,0)
 const input=document.querySelector('input')
 await act(()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,'09/2026');input.dispatchEvent(new window.Event('input',{bubbles:true}))})
 assert.equal(document.querySelectorAll('article').length,1)
 await act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Xem chi tiết').click())
 await act(()=>[...document.querySelectorAll('button')].find(b=>b.textContent==='Sửa bảng lương').click())
 assert.deepEqual(actions,[['view','exact/sep'],['edit','exact/sep']])
 await act(()=>root.render(React.createElement(mod.exports.default,{items,onView:props.onView})))
 assert.equal([...document.querySelectorAll('button')].some(b=>b.textContent==='Sửa bảng lương'),false)
})
