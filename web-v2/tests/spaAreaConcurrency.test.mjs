import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/SpaManagementPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react','react/jsx-runtime','react-dom','lucide-react'], loader: { '.css':'empty' },
  plugins: [{name:'fixture',setup(b){
    b.onResolve({filter:/\/(api|usePageRefresh|UiToolbar|UiCustomText)$/},args=>({path:args.path.split('/').at(-1),namespace:'fixture'}))
    b.onLoad({filter:/.*/,namespace:'fixture'},args=>({loader:'js',contents:
      args.path==='api'?'export const veraApi=globalThis.__areaApi;':
      args.path==='usePageRefresh'?'export default function Hook(){}':
      args.path==='UiCustomText'?'export default function Text({children}){return children}':
      'import React from "react"; export default function Toolbar({children,...props}){return React.createElement("div",props,children)}'}))
  }}],
})

async function fixture() {
  const dom=new JSDOM('<body><div id="root"></div></body>',{pretendToBeVisual:true})
  dom.window.HTMLDialogElement.prototype.showModal=function(){this.open=true}
  dom.window.confirm=()=>true
  const initial={id:'room-1',name:'1',kind:'room',version:'v1',beds:[{id:'bed-1',name:'1.1',booking_name:'1.1',active:true}]}
  let server=structuredClone(initial),revision=1,locks=0,readFails=false
  const calls=[]
  const api={
    spaSettings:async()=>{if(readFails)throw Error('Read unavailable'); return {revision,services:[],combos:[],service_areas:[structuredClone(server)]}},
    liveTourAction:async body=>{
      calls.push(structuredClone(body))
      if(locks-- > 0)throw Object.assign(Error('Tài nguyên đang được cập nhật. Vui lòng thử lại.'),{status:503})
      if(body.payload.expected_area_version!==server.version)throw Object.assign(Error('Khu vực này vừa được người khác sửa hoặc xóa.'),{status:409,payload:{detail:{code:'LIVE_TOUR_AREA_CHANGED'}}})
      server={...server,beds:body.payload.beds.map((b,i)=>({...b,id:b.id||`new-${i}`})),version:'v3'}
      revision+=1
      return {ok:true,revision,result:{service_area:structuredClone(server)}}
    },
  }
  const values={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,__areaApi:api}
  const descriptors=Object.fromEntries(Object.keys(values).map(key=>[key,Object.getOwnPropertyDescriptor(globalThis,key)]))
  for(const [key,value] of Object.entries(values))Object.defineProperty(globalThis,key,{value,writable:true,configurable:true})
  const module={exports:{}}
  new Function('require','module','exports',built.outputFiles[0].text)(require,module,module.exports)
  const {createRoot}=await import('react-dom/client')
  const root=createRoot(dom.window.document.querySelector('#root'))
  await act(async()=>root.render(React.createElement(module.exports.default,{user:{role:'admin'},mode:'settings',initialTab:'areas'})))
  const button=label=>[...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.trim()===label)
  await act(async()=>button('Sửa').click())
  return {doc:dom.window.document,calls,button,
    async click(label){await act(async()=>button(label).click())},
    async change(label,value){const node=dom.window.document.querySelector(`[aria-label="${label}"]`);await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new dom.window.Event('input',{bubbles:true}))})},
    otherUser(){server.beds.push({id:'other-bed',name:'Other bed'});server.version='v2';revision+=1},
    busyOnce(){locks=1},failRefresh(){readFails=true},confirm(value){dom.window.confirm=()=>value},
    async settle(){await act(async()=>{await new Promise(resolve=>setTimeout(resolve,260))})},
    async close(){await act(async()=>root.unmount());dom.window.close();for(const [key,desc]of Object.entries(descriptors)){if(desc)Object.defineProperty(globalThis,key,desc);else delete globalThis[key]}},
  }
}

test('adding a bed uses an area precondition and one compact request; busy retry keeps identical intent',async()=>{
  const f=await fixture()
  try {
    await f.click('Thêm giường')
    await f.change('Tên giường 2','1.2')
    f.busyOnce()
    await f.click('Lưu thay đổi');await f.settle()
    assert.equal(f.calls.length,2)
    assert.deepEqual(f.calls[0],f.calls[1])
    assert.equal(f.calls[0].response_view,'receipt')
    assert.equal(f.calls[0].payload.expected_area_version,'v1')
    assert.equal(f.calls[0].payload.beds[1].name,'1.2')
    assert.equal(f.doc.querySelector('dialog'),null)
    assert.match(f.doc.body.textContent,/Đã lưu thay đổi/)
  } finally {await f.close()}
})

test('real area conflicts preserve the draft and original token until explicitly reopening latest',async()=>{
  const f=await fixture()
  try {
    await f.click('Thêm giường');await f.change('Tên giường 2','My draft')
    f.otherUser()
    await f.click('Lưu thay đổi')
    assert.equal(f.calls.length,1,'a 409 must not auto-retry')
    assert.equal(f.doc.querySelector('[aria-label="Tên giường 2"]').value,'My draft')
    await f.click('Lưu thay đổi')
    assert.equal(f.calls[1].expected_revision,2)
    assert.equal(f.calls[1].payload.expected_area_version,'v1','refreshing list cannot rebase the stale form')
    assert.equal(f.calls[1].idempotency_key,f.calls[0].idempotency_key)
    f.confirm(false);await f.click('Mở bản mới nhất')
    assert.equal(f.doc.querySelector('[aria-label="Tên giường 2"]').value,'My draft')
    f.confirm(true);await f.click('Mở bản mới nhất')
    assert.equal(f.doc.querySelector('[aria-label="Tên giường 2"]').value,'Other bed')
    await f.click('Thêm giường');await f.change('Tên giường 3','My new bed')
    await f.click('Lưu thay đổi')
    assert.equal(f.calls.at(-1).payload.expected_area_version,'v2')
    assert.equal(f.calls.at(-1).payload.beds.length,3)
    assert.equal(f.doc.querySelector('dialog'),null)
  } finally {await f.close()}
})

test('confirmed save stays successful when refreshing the settings list fails',async()=>{
  const f=await fixture()
  try {
    f.failRefresh()
    await f.click('Thêm giường');await f.click('Lưu thay đổi')
    assert.equal(f.calls.length,1)
    assert.equal(f.doc.querySelector('dialog'),null)
    assert.match(f.doc.body.textContent,/Đã lưu thành công nhưng chưa tải được/)
  } finally {await f.close()}
})
