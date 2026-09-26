import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const dom = new JSDOM('<body><div id="root"></div></body>',{url:'https://example.test',pretendToBeVisual:true})
Object.defineProperties(globalThis,{window:{value:dom.window,configurable:true},document:{value:dom.window.document,configurable:true},navigator:{value:dom.window.navigator,configurable:true},IS_REACT_ACT_ENVIRONMENT:{value:true,configurable:true}})
const {createRoot}=await import('react-dom/client')
const built=await build({entryPoints:[fileURLToPath(new URL('../src/components/LongLeaveAdminPanel.jsx',import.meta.url))],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',external:['react','react/jsx-runtime','react-dom','lucide-react'],loader:{'.css':'empty'},define:{'import.meta.env.VITE_VERA_API_BASE_URL':'"https://api.test"'},plugins:[{name:'session',setup(b){b.onResolve({filter:/\/lib\/supabase$/},()=>({path:'session',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export async function getCurrentSession(){return {access_token:"test"}}',loader:'js'}))}}]})
const module={exports:{}}
new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),module,module.exports)
test('annual card checks its own future dates and shows people and counts without approving',async()=>{
  const original=globalThis.fetch,calls=[],root=createRoot(document.querySelector('#root'))
  globalThis.fetch=async(url,options)=>{
    calls.push([url,options.method||'GET'])
    const data=url.endsWith('/pending')?{requests:[{id:'november',employee_name:'Applicant',request_type:'Nghỉ Phép năm',start_date:'2026-11-20',end_date:'2026-11-26',days:7}]}:
      url.includes('/requests/november/overlap')?{start:'2026-11-20',end:'2026-11-26',employee_count:1,peak_with_applicant:2,days:[{date:'2026-11-21',other_count:1,approved_count:1,pending_count:0}],requests:[{id:'other',employee_name:'Other',full_name:'Employee Test',request_type:'Nghỉ Phép năm',status:'Đã duyệt',start_date:'2026-11-21',end_date:'2026-11-21'}]}:{days:[]}
    return {ok:true,json:async()=>data}
  }
  try{
    await act(async()=>root.render(React.createElement(module.exports.default,{user:{role:'admin'}})))
    assert.ok(!calls.some(([url])=>url.includes('/requests/')))
    const card=document.querySelector('.long-leave-pending-card')
    await act(async()=>[...card.querySelectorAll('button')].find(node=>node.textContent==='Kiểm tra').click())
    assert.equal(calls.filter(([url])=>url.endsWith('/requests/november/overlap')).length,1)
    const result=card.querySelector('[aria-label="Kết quả kiểm tra november"]')
    assert.match(result.textContent,/1 nhân viên khác nghỉ trong 20-11-2026 – 26-11-2026/)
    assert.match(result.textContent,/Cao nhất 2 người/)
    assert.match(result.textContent,/Employee Test/)
    assert.ok(calls.every(([,method])=>method==='GET'))
  }finally{await act(()=>root.unmount());globalThis.fetch=original}
})
