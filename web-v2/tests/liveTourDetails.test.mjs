import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import { JSDOM } from 'jsdom'
import React,{act} from 'react'

const built=await build({entryPoints:['src/lib/useLiveTourDetails.js'],bundle:true,write:false,platform:'node',format:'cjs',external:['react'],plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const veraApi=globalThis.__detailsApi'}))}}]})

test('loads only active panel, discards superseded requests and retains displayed detail with its original edit revision while the board changes',async()=>{
 const dom=new JSDOM('<div id="root"></div>',{url:'https://test.invalid'})
 for(const [key,value] of Object.entries({window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true}))Object.defineProperty(globalThis,key,{value,configurable:true})
 const requests=[]
 globalThis.__detailsApi={liveTourCollection:(panel,query)=>new Promise(resolve=>requests.push({panel,query,resolve}))}
 const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
 const useDetails=module.exports.default;let latest
 function Screen(props){latest=useDetails(props);return null}
 const {createRoot}=await import('react-dom/client');const root=createRoot(document.querySelector('#root'))
 let props={board:{revision:1,state:{},customers:[]},panel:'catalog',filters:{},customerSearch:'',lookupOpen:false,lookupSearch:''}
 const render=async()=>{await act(async()=>root.render(React.createElement(Screen,props)));await act(async()=>new Promise(resolve=>setTimeout(resolve,210)))}
 try{
  await render();assert.equal(requests.length,0)
  props={...props,panel:'customers',enabled:false};await render();assert.equal(requests.length,0)
  props={...props,enabled:true};await render();assert.equal(requests[0].panel,'customers')
  props={...props,panel:'invoices'};await render();assert.equal(requests[1].panel,'invoices')
  await act(async()=>requests[0].resolve({revision:1,data:{customers:[{id:'old'}]},pages:1,total:1}))
  assert.deepEqual(latest.data.customers,[])
  await act(async()=>requests[1].resolve({revision:1,data:{state:{invoices:[{id:'invoice'}]}},pages:3,total:120}))
  assert.equal(latest.data.state.invoices[0].id,'invoice')
  await act(async()=>latest.setPage(2));await act(async()=>new Promise(resolve=>setTimeout(resolve,210)))
  assert.equal(requests[2].query.page,2)
  props={...props,board:{...props.board,revision:2}};await render()
  await act(async()=>requests[2].resolve({revision:1,data:{state:{invoices:[{id:'stale'}]}},pages:3,total:120}))
  assert.equal(latest.data.state.invoices[0].id,'stale')
  assert.equal(latest.data.revision,1)
  assert.equal(requests.length,3)
 }finally{await act(async()=>root.unmount());dom.window.close();delete globalThis.__detailsApi}
})
