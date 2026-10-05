import test, {after} from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {build} from 'esbuild'
import React, {act} from 'react'
import {JSDOM} from 'jsdom'
const initial = new JSDOM('<body/>')
globalThis.window = initial.window; globalThis.document = initial.window.document
after(() => initial.window.close())
const bundle = await build({stdin:{contents:"export {default as Page} from './src/pages/HcRulesPage'",resolveDir:process.cwd()},bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react-dom','react/jsx-runtime'],loader:{'.css':'empty'},plugins:[{name:'mock-api',setup(b){b.onResolve({filter:/lib\/api$/},()=>({path:'api',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const veraApi={hcRules:()=>globalThis.hcApi.load(),saveHcRules:(...a)=>globalThis.hcApi.save(...a)}'}))}}]})
const mod={exports:{}};new Function('require','module','exports',bundle.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
async function fixture(t, role='admin') {
 const dom=new JSDOM('<body><div id="root"/></body>',{url:'https://example.test'}), saved={}
 let data={revision:0,departments:[{code:'locker',name:'Locker',salary_mode:'hourly',enabled:false},{code:'letan',name:'Lễ tân',salary_mode:'hourly',enabled:false}]},calls=[]
 const api={load:async()=>data,save:async(code,body)=>{calls.push({code,body});data={...data,revision:data.revision+1,departments:data.departments.map(d=>d.code===code?{...d,enabled:body.enabled}:d)};return data}}
 for(const [key,value] of Object.entries({window:dom.window,document:dom.window.document,navigator:dom.window.navigator,IS_REACT_ACT_ENVIRONMENT:true,hcApi:api})) {saved[key]=Object.getOwnPropertyDescriptor(globalThis,key);Object.defineProperty(globalThis,key,{value,configurable:true})}
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.querySelector('#root'))
 t.after(async()=>{await act(()=>root.unmount());dom.window.close();for(const [key,value] of Object.entries(saved)) {if(value)Object.defineProperty(globalThis,key,value);else delete globalThis[key]}})
 await act(async()=>root.render(React.createElement(mod.exports.Page,{user:{role}})))
 return {calls,api,click:async index=>act(async()=>document.querySelectorAll('.hc-department button')[index].click())}
}
test('Admin has independent department activation switches with current revision', async t=>{
 const f=await fixture(t)
 assert.equal(document.querySelectorAll('.hc-department button').length,2)
 await f.click(0)
 assert.deepEqual(f.calls[0],{code:'locker',body:{enabled:true,expected_revision:0}})
 assert.deepEqual([...document.querySelectorAll('.hc-department button')].map(b=>b.getAttribute('aria-pressed')),['true','false'])
 await f.click(1);assert.equal(f.calls[1].body.expected_revision,1)
 await f.click(0);assert.equal(f.calls[2].body.enabled,false)
 assert.match(document.querySelector('[role=status]').textContent,/Locker: đã tắt/)
})
test('non Admin can read the rule but cannot change activation',async t=>{
 await fixture(t,'giamdoc')
 assert.equal(document.querySelectorAll('.hc-department button').length,0)
 assert.match(document.body.textContent,/Nghỉ không phép/)
})
test('failed switch keeps department state and exposes an error', async t=>{
 const f=await fixture(t);f.api.save=async()=>{throw Error('Nội quy đã thay đổi. Hãy làm mới rồi thử lại.')}
 await f.click(0)
 assert.equal(document.querySelector('.hc-department button').getAttribute('aria-pressed'),'false')
 assert.match(document.querySelector('[role=alert]').textContent,/Nội quy đã thay đổi/)
})
