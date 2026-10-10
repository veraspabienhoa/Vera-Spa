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
    assert.equal(observed.loading,true,'the newer board revision is still queued')
    await act(delay)
    assert.equal(calls.length,2,'one trailing read catches the last revision even if polling stops')
    await act(async()=>calls[1].resolve(result(10)))
    assert.equal(observed.data.revision,10)
    assert.equal(observed.loading,false)
    await act(()=>root.render(React.createElement(Probe,{...props,board:board(10),filters:{employee:'An'}})))
    await act(delay)
    assert.equal(calls.length,3)
    await act(()=>root.render(React.createElement(Probe,{...props,board:board(10),filters:{employee:'An An'}})))
    assert.equal(calls[2].options.signal.aborted,true)
    await act(delay)
    assert.equal(calls.length,4)
    await act(async()=>calls[2].resolve(result(8)))
    assert.equal(observed.total,0,'obsolete response must never replace current filter')
    await act(async()=>calls[3].resolve(result(10)))
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
      canExportKind:()=>false,exportData:()=>{},invoiceTotal:details.total,page:details.page,pages:details.pages,asArray:value=>value||[],formatMoney:String}) : null
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

function detailProbe(initial) {
  const calls=[]
  globalThis.__detailsApi={liveTourCollection:(panel,query,options)=>new Promise((resolve,reject)=>calls.push({panel,query,options,resolve,reject}))}
  const local={exports:{}}
  new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),local,local.exports)
  let latest
  let props={board:board(1),panel:'catalog',filters:{},lookupOpen:false,...initial}
  function Probe(value){latest=local.exports.default(value);return null}
  const root=createRoot(document.querySelector('#root'))
  return {calls,get latest(){return latest},
    async render(changes={}){props={...props,...changes};await act(()=>root.render(React.createElement(Probe,props)))},
    async settle(callback){await act(async()=>callback())},
    async wait(){await act(delay)},
    async unmount(){await act(()=>root.unmount())},
  }
}

const customerResult=(revision,...ids)=>({revision,data:{customers:ids.map(id=>({id,name:id,combo_purchases:[{id:`p-${id}`,booking_remaining:revision}]}))}})

test('slow lookup batches finish across revision bursts and catch up once without abort/restart starvation', async()=>{
  const f=detailProbe({lookupOpen:true,lookupSearch:'search',selectedCustomerIds:['c1','c2','c1']})
  try {
    await f.render();await f.wait()
    assert.equal(f.calls.length,2)
    assert.equal(f.calls[1].query.customer_ids,'c1,c2')
    for(let revision=2;revision<=20;revision++) await f.render({board:board(revision)})
    await f.wait()
    assert.equal(f.calls.length,2)
    assert.equal(f.calls[0].options.signal.aborted,false)
    assert.equal(f.calls[1].options.signal.aborted,false)
    await f.settle(()=>{f.calls[0].resolve(customerResult(1,'match'));f.calls[1].resolve(customerResult(1,'c1','c2'))})
    assert.deepEqual(f.latest.data.customers,[],'stale reservations stay hidden until the queued read finishes')
    await f.wait()
    assert.equal(f.calls.length,4,'exactly one search/selected-customer batch follows the burst')
    await f.settle(()=>{f.calls[2].resolve(customerResult(20,'match'));f.calls[3].resolve(customerResult(20,'c1','c2'))})
    assert.deepEqual(f.latest.data.customers.map(row=>row.id),['match','c1','c2'])
    assert.equal(f.latest.data.customers[1].combo_purchases[0].booking_remaining,20)
    await f.wait()
    assert.equal(f.calls.length,4)
  } finally {await f.unmount()}
})

test('lookup freshness uses the oldest actual response revision, not the board revision captured at completion', async()=>{
  const f=detailProbe({board:board(5),lookupOpen:true,selectedCustomerId:'selected'})
  try {
    await f.render();await f.wait()
    await f.settle(()=>{f.calls[0].resolve(customerResult(5,'match'));f.calls[1].resolve(customerResult(4,'selected'))})
    assert.deepEqual(f.latest.data.customers,[],'an older selected-customer response cannot expose stale combo balances')
    await f.render({board:board(6)});await f.wait()
    await f.render({board:board(7)})
    await f.settle(()=>{f.calls[2].resolve(customerResult(7,'match'));f.calls[3].resolve(customerResult(7,'selected'))})
    assert.equal(f.latest.data.customers[1].combo_purchases[0].booking_remaining,7)
    await f.wait()
    assert.equal(f.calls.length,4,'responses already at the latest revision satisfy queued invalidations')
  } finally {await f.unmount()}
})

test('failed lookup batches wait for the other request, recover the queued revision, and stop after a final error', async()=>{
  const f=detailProbe({lookupOpen:true,selectedCustomerId:'selected'})
  try {
    await f.render();await f.wait()
    await f.render({board:board(2)})
    await f.settle(()=>f.calls[0].reject(Object.assign(new Error('Lookup timeout'),{name:'TimeoutError'})))
    await f.wait()
    assert.equal(f.calls.length,2,'one failed sibling cannot start an overlapping batch')
    await f.settle(()=>f.calls[1].resolve(customerResult(1,'selected')))
    await f.wait()
    assert.equal(f.calls.length,4,'failure releases the coalesced refresh after both reads settle')
    await f.settle(()=>{f.calls[2].reject(new Error('Network offline'));f.calls[3].reject(new Error('Network offline'))})
    assert.equal(f.latest.error,'Network offline')
    await f.wait()
    assert.equal(f.calls.length,4,'do not create an unbounded error retry loop')
    await f.render({board:board(3)});await f.wait()
    await f.settle(()=>{f.calls[4].resolve(customerResult(3,'match'));f.calls[5].resolve(customerResult(3,'selected'))})
    assert.equal(f.latest.error,'')
    assert.equal(f.latest.data.customers[1].id,'selected')
  } finally {await f.unmount()}
})

test('date navigation cancels old reads and queued refreshes; obsolete success and failure cannot affect the new date', async()=>{
  const f=detailProbe({panel:'invoices',filters:{date_from:'2026-10-01',date_to:'2026-10-01'}})
  try {
    await f.render();await f.wait()
    await f.render({board:board(2)})
    await f.render({filters:{date_from:'2026-10-02',date_to:'2026-10-02'}})
    assert.equal(f.calls[0].options.signal.aborted,true)
    await f.wait()
    assert.equal(f.calls.length,2)
    assert.equal(f.calls[1].query.date_from,'2026-10-02')
    await f.settle(()=>f.calls[1].resolve({...result(2),total:2}))
    await f.settle(()=>f.calls[0].reject(new Error('Obsolete date failed')))
    assert.equal(f.latest.total,2)
    assert.equal(f.latest.error,'')
    await f.wait()
    assert.equal(f.calls.length,2,'old date cannot launch its queued catch-up')
    await f.render({filters:{date_from:'2026-10-03',date_to:'2026-10-03'}});await f.wait()
    await f.render({filters:{date_from:'2026-10-04',date_to:'2026-10-04'}});await f.wait()
    await f.settle(()=>f.calls[2].resolve({...result(3),total:300}))
    assert.equal(f.latest.ready,false)
    await f.settle(()=>f.calls[3].resolve({...result(4),total:4}))
    assert.equal(f.latest.total,4)
    assert.equal(f.latest.data.revision,4)
  } finally {await f.unmount()}
})

test('search/selection changes and closing the lookup suppress obsolete responses and trailing work', async()=>{
  const f=detailProbe({lookupOpen:true,lookupSearch:'old',selectedCustomerId:'old-selected'})
  let mounted=true
  try {
    await f.render();await f.wait()
    await f.render({lookupSearch:'new',selectedCustomerId:'new-selected'});await f.wait()
    assert.equal(f.calls[0].options.signal.aborted,true)
    assert.equal(f.calls[1].options.signal.aborted,true)
    assert.equal(f.calls[2].query.search,'new')
    assert.equal(f.calls[3].query.customer_ids,'new-selected')
    await f.settle(()=>{f.calls[0].resolve(customerResult(1,'old'));f.calls[1].resolve(customerResult(1,'old-selected'))})
    assert.deepEqual(f.latest.data.customers,[])
    await f.settle(()=>{f.calls[2].resolve(customerResult(1,'new'));f.calls[3].resolve(customerResult(1,'new-selected'))})
    assert.deepEqual(f.latest.data.customers.map(row=>row.id),['new','new-selected'])
    await f.render({board:board(2)})
    await f.render({lookupOpen:false});await f.wait()
    assert.equal(f.calls.length,4,'closing clears a scheduled revision refresh')
    assert.deepEqual(f.latest.data.customers,[])
    await f.render({lookupOpen:true});await f.wait()
    assert.equal(f.calls.length,6)
    await f.render({board:board(3)})
    await f.unmount();mounted=false
    assert.equal(f.calls[4].options.signal.aborted,true)
    assert.equal(f.calls[5].options.signal.aborted,true)
    await f.settle(()=>{f.calls[4].resolve(customerResult(3,'late'));f.calls[5].reject(new Error('Late failure'))})
    await f.wait()
    assert.equal(f.calls.length,6,'unmount cannot start a trailing lookup')
    assert.deepEqual(f.latest.data.customers,[])
    assert.equal(f.latest.error,'')
  } finally {if(mounted)await f.unmount()}
})

test('disabling details during an action aborts both readers and ignores late state before re-enabling', async()=>{
  const f=detailProbe({panel:'invoices',lookupOpen:true})
  try {
    await f.render();await f.wait()
    assert.equal(f.calls.length,2)
    await f.render({board:board(2)})
    await f.render({enabled:false})
    assert.equal(f.calls[0].options.signal.aborted,true)
    assert.equal(f.calls[1].options.signal.aborted,true)
    await f.settle(()=>{f.calls[0].resolve(result(1));f.calls[1].resolve(customerResult(1,'old'))})
    await f.wait()
    assert.equal(f.calls.length,2)
    assert.equal(f.latest.ready,false)
    assert.equal(f.latest.loading,false)
    await f.render({enabled:true});await f.wait()
    assert.equal(f.calls.length,4)
    await f.settle(()=>{f.calls[2].resolve(result(2));f.calls[3].resolve(customerResult(2,'current'))})
    assert.equal(f.latest.data.revision,2)
    assert.equal(f.latest.data.customers[0].id,'current')
  } finally {await f.unmount()}
})

test('a response without revision keeps its original request version while a newer board is queued', async()=>{
  const f=detailProbe({panel:'invoices'})
  try {
    await f.render();await f.wait()
    await f.render({board:board(2)})
    await f.settle(()=>f.calls[0].resolve({data:{state:{invoices:[{id:'legacy-response'}]}},total:1,pages:1}))
    assert.equal(f.latest.data.revision,1,'never stamp old editable data with the newest board revision')
    await f.wait()
    await f.settle(()=>f.calls[1].resolve(result(2)))
    assert.equal(f.latest.data.revision,2)
  } finally {await f.unmount()}
})

test('a successful lookup cannot clear a detail failure, and a newer revision recovers the failed detail', async()=>{
  const f=detailProbe({panel:'invoices',lookupOpen:true})
  try {
    await f.render();await f.wait()
    await f.settle(()=>f.calls[0].reject(Object.assign(new Error('Invoice timeout'),{name:'TimeoutError'})))
    await f.settle(()=>f.calls[1].resolve(customerResult(1,'current')))
    assert.equal(f.latest.error,'Invoice timeout')
    assert.equal(f.latest.ready,false)
    assert.equal(f.latest.loading,false)
    await f.render({board:board(2)});await f.wait()
    await f.settle(()=>{f.calls[2].resolve(result(2));f.calls[3].resolve(customerResult(2,'current'))})
    assert.equal(f.latest.error,'')
    assert.equal(f.latest.ready,true)
  } finally {await f.unmount()}
})
