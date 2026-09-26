import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'
import { customerComboRows, latestCustomerPurchase } from '../src/lib/customerComboRows.js'
const customers=[{id:'c',name:'Khách thử',phone:'0901000001',combo_purchases:[{id:'new',combo_name:'Combo mới',remaining:12,purchased_at:'2026-09-26T10:00:00+07:00'},{id:'old',combo_name:'Combo cũ',remaining:2,purchased_at:'2026-09-01T10:00:00+07:00'},{id:'used',remaining:0},{id:'deleted',remaining:10,deleted_at:'2026-09-27'}]}]
const built=await build({stdin:{contents:`import React,{act,useState} from 'react';import {createRoot} from 'react-dom/client';import Fields from './src/components/ComboCustomerFields';import Gallery from './src/pages/MobileStationPanel';import Picker from './src/components/AttendanceCodePicker';import Spa from './src/pages/SpaManagementPage';
function Form(){const[draft,setDraft]=useState({customer_name:'',customer_phone:'',combo_ticket:''});window.draft=draft;return <Fields customers={window.customers} draft={draft} setDraft={setDraft}/>}
window.testAct=act;window.mount=kind=>{window.root=createRoot(document.getElementById('root'));window.root.render(kind==='combo'?<Form/>:kind==='gallery'?<Gallery registry={{devices:[]}} canOperate={false} canDeletePhotos/>:kind==='customers'?<Spa mode="customers" user={{role:'admin',permissions:{live_tour_customers_view:true}}}/>:<Picker onChoose={(...args)=>window.chosen=args}/>)};`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const veraApi=window.testApi;',loader:'js'}))}}]})
async function page(context,kind,api={}){
 const dom=new JSDOM('<div id="root"></div>',{url:'https://test.invalid',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window,channels=[]
 w.MessageChannel=class extends MessageChannel{constructor(){super();channels.push(this)}}
 w.IS_REACT_ACT_ENVIRONMENT=true;w.testApi=api;w.customers=customers;w.confirm=()=>true;w.HTMLElement.prototype.scrollIntoView=()=>{}
 w.eval(built.outputFiles[0].text);await w.testAct(async()=>w.mount(kind))
 context.after(async()=>{await w.testAct(async()=>w.root.unmount());channels.forEach(c=>{c.port1.close();c.port2.close()});w.close()})
 return {w,doc:w.document,async click(node){assert.ok(node);await w.testAct(async()=>node.click())},button(label){return [...w.document.querySelectorAll('button')].find(b=>b.textContent.trim()===label)},async input(node,value){await w.testAct(async()=>{Object.getOwnPropertyDescriptor(w.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new w.Event('input',{bubbles:true}))})}}
}
test('name or phone selects canonical customer and newest purchase; editing search clears stale combo',async ctx=>{
 const p=await page(ctx,'combo'),inputs=p.doc.querySelectorAll('[role=combobox]')
 await p.input(inputs[1],'0901000');await p.click(p.doc.querySelector('[role=option][id]'))
 assert.equal(p.w.draft.customer_name,'Khách thử');assert.equal(p.w.draft.customer_phone,'0901000001');assert.equal(p.w.draft.combo_purchase_id,'new');assert.match(p.w.draft.combo_ticket,/còn 12 vé/)
 await p.input(inputs[0],'Khách');assert.equal(p.w.draft.combo_purchase_id,'');assert.equal(p.w.draft.combo_ticket,'')
 await p.click(p.doc.querySelector('[role=option][id]'));assert.equal(p.w.draft.combo_purchase_id,'new');assert.equal(latestCustomerPurchase(customers[0]).id,'new')
})
test('customer table renders each remaining purchase in its own row',async ctx=>{
 assert.equal(customerComboRows(customers).length,2)
 const p=await page(ctx,'customers',{spaCustomers:async()=>({revision:1,customers,combo_catalog:[]})})
 const rows=p.doc.querySelectorAll('.spa-customers-table tbody tr')
 assert.equal(rows.length,2);assert.match(rows[0].textContent,/Combo mới · còn 12 vé/);assert.match(rows[1].textContent,/Combo cũ · còn 2 vé/)
})
test('photo-only role can delete image, with stale refresh suppressed and capture controls hidden',async ctx=>{
 let reads=0,late,deleted=0
 const row={id:'photo',event_type:'photo',has_image:true,occurred_at:'2026-09-26T10:00:00+07:00'}
 const p=await page(ctx,'gallery',{mobileStationEvents:()=>++reads===1?Promise.resolve({records:[row]}):new Promise(resolve=>late=resolve),deleteMobileStationImage:async()=>{deleted++}})
 assert.equal(p.button('Bật camera'),undefined);await p.click(p.button('Làm mới'));await p.click(p.button('Xóa ảnh'));assert.equal(deleted,1);assert.equal(p.button('Xem ảnh'),undefined)
 await p.w.testAct(async()=>late({records:[row]}));assert.equal(p.button('Xem ảnh'),undefined)
})
test('code catalogue only allows a uniquely matched attendance code to fill mapping',async ctx=>{
 const p=await page(ctx,'picker',{attendanceCodes:async()=>({matched_count:1,total_count:2,employees:[{username:'A',full_name:'Alpha',status:'matched',codes:[{attendance_code:'00123',employee_code:'EMP001'}]},{username:'B',status:'conflict',codes:[{attendance_code:'00321',employee_code:''}]}]})})
 await p.click(p.button('Lấy mã TimeSoft đã đồng bộ'));assert.equal([...p.doc.querySelectorAll('button')].filter(b=>b.textContent==='Chọn mã').length,1)
 await p.click(p.button('Chọn mã'));assert.deepEqual(Array.from(p.w.chosen),['A','00123'])
})
