import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { pageModuleLoader } from '../src/lib/pageModuleLoader.js'
const require=createRequire(import.meta.url)
const directory=fileURLToPath(new URL('../',import.meta.url))
const built=await build({stdin:{contents:`export {default as Text} from './src/components/UiCustomText'; export {default as Content} from './src/components/PageContent'; export {default as useTablePage} from './src/lib/useTablePage'; export {default as Pager} from './src/components/TablePager'; export {publishCustomization} from './src/lib/uiCustomizationStore'`,resolveDir:directory},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime','react-dom'],loader:{'.css':'empty'}})
async function fixture(){
 const dom=new JSDOM('<body><div id="root"></div></body>'), names=['window','document','navigator','IS_REACT_ACT_ENVIRONMENT']
 const saved=Object.fromEntries(names.map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
 for(const [k,v] of Object.entries({window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true}))Object.defineProperty(globalThis,k,{value:v,configurable:true})
 const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(require,module,module.exports)
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
 return {...module.exports,root,doc:document,async close(){await act(()=>root.unmount());dom.window.close();for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}}}
}
test('shell clock updates do not render the business page again',async()=>{
 const f=await fixture();let renders=0
 const body=()=>{renders++;return React.createElement('p',null,'Business page')},toggle=React.createElement('button',null,'Menu')
 try{
  for(let tick=0;tick<20;tick++)await act(()=>f.root.render(React.createElement('div',null,React.createElement('span',null,tick),React.createElement(f.Content,{navigationToggle:toggle},body))))
  assert.equal(renders,1)
  await act(()=>f.root.render(React.createElement(f.Content,{navigationToggle:toggle},()=>React.createElement('p',null,'New page'))))
  assert.match(f.doc.body.textContent,/New page/)
 }finally{await f.close()}
})
test('repeated custom labels resolve their own owner without whole-document scans or unrelated rerenders',async()=>{
 const f=await fixture();let scans=0,commits=0
 const original=f.doc.querySelectorAll.bind(f.doc);f.doc.querySelectorAll=(...args)=>{scans++;return original(...args)}
 try{
  f.publishCustomization({same:{label:'Open'}})
  await act(()=>f.root.render(React.createElement(React.Profiler,{id:'labels',onRender:()=>commits++},Array.from({length:1000},(_,i)=>React.createElement('button',{'data-ui-key':'same','aria-label':'Original',key:i},React.createElement(f.Text,{uiKey:'same'},'Xem'))))))
  assert.equal(scans,0);assert.equal(original('button[aria-label="Open"]').length,1000)
  const count=commits;await act(()=>f.publishCustomization({same:{label:'Open'},other:{label:'Changed'}}));assert.equal(commits,count)
  await act(()=>f.publishCustomization({}));assert.equal(original('button[aria-label="Original"]').length,1000)
 }finally{await f.close()}
})
test('3000 rows mount only 100; totals, later pages and filter resets stay correct',async()=>{
 const f=await fixture();const all=Array.from({length:3000},(_,i)=>({id:i+1,amount:10}));let current
 function Table({scope,rows}){const page=f.useTablePage(rows,scope);current=page;return React.createElement('div',null,React.createElement('output',null,rows.reduce((n,r)=>n+r.amount,0)),React.createElement(f.Pager,{pagination:page}),React.createElement('table',null,React.createElement('tbody',null,page.rows.map(r=>React.createElement('tr',{key:r.id},React.createElement('td',null,r.id))))))}
 try{
  await act(()=>f.root.render(React.createElement(Table,{scope:'all',rows:all})));assert.equal(f.doc.querySelectorAll('tbody tr').length,100);assert.equal(f.doc.querySelector('output').textContent,'30000')
  await act(()=>current.setPage(30));assert.equal(f.doc.querySelector('td').textContent,'2901')
  await act(()=>f.root.render(React.createElement(Table,{scope:'filtered',rows:all.slice(0,20)})));assert.equal(f.doc.querySelector('td').textContent,'1');assert.equal(f.doc.querySelectorAll('tbody tr').length,20)
  await act(()=>f.root.render(React.createElement(Table,{scope:'all',rows:all})));assert.equal(f.doc.querySelector('td').textContent,'1')
 }finally{await f.close()}
})
test('module prefetch is shared with opening the page and failed imports can retry',async()=>{
 let calls=0;const module={default:()=>null},load=pageModuleLoader(async()=>{calls++;return module})
 const first=load(),second=load();assert.equal(first,second);assert.equal(await first,module);await load();assert.equal(calls,1)
 let attempts=0;const retry=pageModuleLoader(async()=>{attempts++;if(attempts===1)throw Error('offline');return module})
 await assert.rejects(retry(),/offline/);assert.equal(await retry(),module);assert.equal(attempts,2)
})
