import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'
const result=await build({stdin:{contents:`import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Export from './src/components/LiveTourInvoiceExport';window.act=act;const root=createRoot(document.getElementById('root'));window.mount=()=>act(async()=>root.render(<Export datePolicy={{sections:{invoices:['all','today']}}} onClose={()=>{}}/>));window.unmount=()=>act(async()=>root.unmount());`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'mock',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:`export const veraApi={liveTourCollection:async(panel,query)=>{window.query=query;return {data:{state:{invoices:[{id:'a',bill_no:'VERA-A',total:300,tip:100,subtotal:200,entries:[{service:'VIP'}]},{id:'b',bill_no:'VERA-B',total:400,tip:150,subtotal:250,entries:[{service:'Body'}]}]}},pages:1}},exportSelectedInvoices:async(format,body)=>{window.exported={format,body};return new Blob(['file'])}};`}))}}]})
test('select multiple invoices, choose tip only and export without QR',async()=>{
const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true});const w=dom.window
w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}};w.IS_REACT_ACT_ENVIRONMENT=true;w.URL.createObjectURL=()=> 'blob:test';w.URL.revokeObjectURL=()=>{};w.eval(result.outputFiles[0].text)
try {
 await w.mount();await w.act(async()=>new Promise(r=>setTimeout(r,350)))
 for(const label of ['Chọn VERA-A','Chọn VERA-B']) await w.act(async()=>w.document.querySelector(`[aria-label="${label}"]`).click())
 assert.equal(w.document.querySelectorAll('.invoice-export-receipt').length,1)
 assert.equal(w.document.querySelectorAll('.invoice-export-receipt tbody tr').length,2)
 assert.match(w.document.querySelector('.invoice-export-receipt tfoot').textContent,/700/)
 await w.act(async()=>w.document.querySelector('.invoice-export-options input').click())
 const view=[...w.document.querySelectorAll('button')].find(b=>b.textContent==='Xem PNG')
 await w.act(async()=>view.click())
 assert.deepEqual(Array.from(w.exported.body.ids),['a','b']);assert.equal(w.exported.body.service,false);assert.equal(w.exported.body.tip,true)
 assert.equal(w.document.querySelectorAll('.invoice-export-table tbody tr').length,2)
 assert.ok(w.document.querySelector('img[alt="Các hóa đơn đã chọn"]'))
 assert.equal(w.document.querySelector('.live-tour-payment-qr'),null)
 assert.ok(w.document.querySelector('.invoice-file-modal[role="dialog"] img'))
 assert.equal(w.document.querySelector('.invoice-export-receipt-panel .invoice-export-preview'),null)
 await w.act(async()=>w.document.querySelector('.invoice-file-modal button').click())
 assert.equal(w.document.querySelector('.invoice-file-modal'),null)
 assert.equal(w.document.querySelectorAll('.invoice-export-table tbody input:checked').length,2)
 const pdf=[...w.document.querySelectorAll('button')].find(b=>b.textContent==='Xem PDF')
 await w.act(async()=>pdf.click())
 const dialog=w.document.querySelector('.invoice-file-modal')
 assert.ok(dialog.querySelector('iframe[title="Xem hóa đơn PDF"]'))
 await w.act(async()=>dialog.dispatchEvent(new w.KeyboardEvent('keydown',{key:'Escape',bubbles:true,cancelable:true})))
 assert.equal(w.document.querySelector('.invoice-file-modal'),null)
 assert.ok(w.document.querySelector('.invoice-export-modal'))
}finally{await w.unmount();w.close()}
})
