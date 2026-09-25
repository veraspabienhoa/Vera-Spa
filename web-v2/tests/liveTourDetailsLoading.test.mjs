import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { createRequire } from 'node:module'
import React, {act} from 'react'
import {JSDOM} from 'jsdom'
const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test'})
Object.assign(globalThis,{window:dom.window,document:dom.window.document,IS_REACT_ACT_ENVIRONMENT:true})
const {createRoot}=await import('react-dom/client')
const built=await build({entryPoints:['src/lib/useLiveTourDetails.js'],bundle:true,write:false,platform:'node',format:'cjs',external:['react'],plugins:[{name:'fixture',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const veraApi=globalThis.__detailsApi'}))}}]})
const delay=()=>new Promise(resolve=>setTimeout(resolve,210))
const board=revision=>({revision,state:{employees:[]},customers:[]})
const result=revision=>({revision,data:{state:{invoices:[{id:'paid'}]}},pages:1,total:1})
let observed

test('board polling cannot starve a slower invoice request; filtered reads cancel older work', async()=>{
  const calls=[]
  globalThis.__detailsApi={liveTourCollection:(panel,query,options)=>new Promise(resolve=>calls.push({panel,query,options,resolve}))}
  const local={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),local,local.exports)
  function Probe(props){observed=local.exports.default(props);return null}
  const root=createRoot(document.querySelector('#root'))
  const props={board:board(7),panel:'invoices',filters:{employee:''},lookupOpen:false}
  try{
    await act(()=>root.render(React.createElement(Probe,props)))
    await act(delay)
    assert.equal(calls.length,1)
    for(const revision of [8,9,10]) await act(()=>root.render(React.createElement(Probe,{...props,board:board(revision)})))
    await act(delay)
    assert.equal(calls.length,1)
    assert.equal(calls[0].options.signal.aborted,false)
    await act(async()=>calls[0].resolve(result(7)))
    assert.equal(observed.data.state.invoices[0].id,'paid')
    assert.equal(observed.data.revision,7,'edits keep the version of the displayed invoice')
    assert.equal(observed.loading,false)
    await act(()=>root.render(React.createElement(Probe,{...props,board:board(10),filters:{employee:'An'}})))
    await act(delay)
    assert.equal(calls.length,2)
    await act(()=>root.render(React.createElement(Probe,{...props,board:board(10),filters:{employee:'An An'}})))
    assert.equal(calls[1].options.signal.aborted,true)
    await act(delay)
    assert.equal(calls.length,3)
    await act(async()=>calls[1].resolve(result(8)))
    assert.equal(observed.total,0,'obsolete response must never replace current filter')
    await act(async()=>calls[2].resolve(result(10)))
    assert.equal(observed.total,1)
  }finally{await act(()=>root.unmount())}
})
