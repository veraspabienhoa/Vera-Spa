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

test('paid invoice heading keeps filtered total 64 on both pages and shows 50 then 14 cards', async()=>{
  const panelBuild=await build({entryPoints:['src/components/LiveTourInvoicesPanel.jsx'],bundle:true,write:false,
    platform:'node',format:'cjs',jsx:'automatic',external:['react'],plugins:[{name:'layout-fixture',setup(b){
      b.onResolve({filter:/\/Ui(Toolbar|CustomText)$/},()=>({path:'layout',namespace:'fixture'}))
      b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'import React from "react"; export default function Layout({children}){return React.createElement("div",null,children)}'}))
    }}]})
  const panelModule={exports:{}}
  new Function('require','module','exports',panelBuild.outputFiles[0].text)(createRequire(import.meta.url),panelModule,panelModule.exports)
  const Panel=panelModule.exports.default
  const requests=[]
  globalThis.__detailsApi={liveTourCollection:(panel,query)=>new Promise(resolve=>requests.push({panel,query,resolve}))}
  const hookModule={exports:{}}
  new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),hookModule,hookModule.exports)
  let details
  function Screen(props){
    details=hookModule.exports.default(props)
    return details.ready ? React.createElement(Panel,{data:details.data,visibleInvoices:details.data.state.invoices,
      invoiceTotal:details.total,page:details.page,pages:details.pages,asArray:value=>value||[],formatMoney:String}) : null
  }
  const root=createRoot(document.querySelector('#root'))
  const props={board:board(1),panel:'invoices',filters:{date_from:'2026-09-26',date_to:'2026-09-26'},lookupOpen:false}
  const response=(start,count,total)=>({revision:1,pages:Math.max(1,Math.ceil(total/50)),total,
    data:{state:{invoices:Array.from({length:count},(_,i)=>({id:`i${start+i}`,bill_no:`HD${start+i}`,
      total:100,effective_at:'2026-09-26T10:00:00+07:00',entries:[]}))}}})
  try{
    await act(()=>root.render(React.createElement(Screen,props)));await act(delay)
    await act(async()=>requests[0].resolve(response(14,50,64)))
    assert.equal(document.querySelector('.live-tour-invoice-count').textContent,'64')
    assert.equal(document.querySelectorAll('.live-tour-data-card').length,50)
    assert.match(document.body.textContent,/50 \/ 64 hóa đơn theo bộ lọc · Trang 1\/2/)
    await act(()=>details.setPage(2));await act(delay)
    assert.equal(document.querySelector('.live-tour-invoice-count'),null,'do not label old page data as a new page')
    await act(async()=>requests[1].resolve(response(0,14,64)))
    assert.equal(document.querySelector('.live-tour-invoice-count').textContent,'64')
    assert.equal(document.querySelectorAll('.live-tour-data-card').length,14)
    assert.match(document.body.textContent,/14 \/ 64 hóa đơn theo bộ lọc · Trang 2\/2/)
    await act(()=>root.render(React.createElement(Screen,{...props,filters:{bill_no:'missing'}})));await act(delay)
    await act(async()=>requests.at(-1).resolve(response(0,0,0)))
    assert.equal(document.querySelector('.live-tour-invoice-count').textContent,'0')
    assert.equal(document.querySelectorAll('.live-tour-data-card').length,0)
  }finally{await act(()=>root.unmount())}
})
