import test from 'node:test'
import assert from 'node:assert/strict'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'
import {combineObligationGroups} from '../src/lib/payrollObligationGroups.js'

const claim={employee_name:'An Nhiên',amount:300000,type:'Âm thực nhận',due_from:'2026-09-16',content:'Nợ âm',status:'Chưa hoàn thành'}
const deferred={employee_name:' AN NHIÊN ',amount:500000,type:'Tạm hoãn vi phạm',due_from:'2026-10-01',content:'Vi phạm',status:'Chưa hoàn thành'}
const groups=[{type:'Âm thực nhận',details:[claim]},{type:'Tạm hoãn vi phạm',details:[deferred]}]
const obligations=[{...deferred,id:'deferred'},{id:'manual',employee_name:'B',amount:100000,due_from:'2026-10-02',content:'Thêm thủ công',status:'Chưa hoàn thành'}]

test('combines both types and manual entries, counting API overlap once without changing sources',()=>{
 const original=JSON.stringify({groups,obligations}),rows=combineObligationGroups(groups,obligations)
 assert.equal(rows.length,2);assert.equal(rows[0].negative,300000);assert.equal(rows[0].deferred,500000);assert.equal(rows[0].total,800000)
 assert.equal(rows[0].details.length,2);assert.equal(rows[0].details[1].id,'deferred');assert.equal(rows[1].total,100000)
 assert.equal(JSON.stringify({groups,obligations}),original)
})
test('identical separate claims stay separate; paid and zero claims are excluded',()=>{
 const duplicated=[{type:'Âm thực nhận',details:[claim,{...claim}]}]
 const rows=combineObligationGroups(duplicated,[{...claim,id:'one'},{...claim,id:'two'},
  {employee_name:'An Nhiên',amount:999999,status:'Đã hoàn thành'}, {employee_name:'An Nhiên',amount:0}])
 assert.equal(rows[0].total,600000);assert.equal(rows[0].details.length,2)
 assert.deepEqual(rows[0].details.map(item=>item.id),['one','two'])
})
test('only one table renders totals, all dates and contents, and targeted delete controls',async()=>{
 const built=await build({stdin:{contents:`import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Table from './src/components/PayrollObligationTable';const root=createRoot(document.getElementById('root'));window.act=act;window.removed=[];window.mount=(groups,obligations=[],disabled=false)=>act(async()=>root.render(<Table groups={groups} obligations={obligations} disabled={disabled} onRemove={id=>window.removed.push(id)}/>));window.unmount=()=>act(async()=>root.unmount());`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic'})
 const dom=new JSDOM('<div id="root"></div>',{url:'https://example.test',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window
 w.IS_REACT_ACT_ENVIRONMENT=true
 w.MessageChannel=class{constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 w.eval(built.outputFiles[0].text)
 try{
  await w.mount(groups,obligations)
  const table=w.document.querySelector('table')
  assert.equal(w.document.querySelectorAll('table').length,1);assert.equal(table.querySelectorAll('tbody > tr').length,2)
  for(const text of ['16-09-2026','01-10-2026','02-10-2026','Nợ âm','Vi phạm','Thêm thủ công','800.000đ','100.000đ'])assert.ok(table.textContent.includes(text),text)
  assert.ok(table.querySelector('tfoot').textContent.includes('900.000đ'))
  await w.act(async()=>w.document.querySelector('[aria-label="Xóa khoản 2 của An Nhiên"]').click())
  assert.deepEqual(Array.from(w.removed),['deferred'])
  await w.mount(groups,obligations,true)
  assert.ok([...w.document.querySelectorAll('button')].every(button=>button.disabled))
  await w.mount([])
  assert.equal(w.document.querySelectorAll('table').length,1)
  assert.ok(w.document.body.textContent.includes('Không có khoản đang mở.'))
  assert.ok(w.document.querySelector('tfoot').textContent.includes('0đ'))
 }finally{await w.unmount();w.close()}
})
