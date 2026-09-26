import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const require = createRequire(import.meta.url)
const built = await build({
  entryPoints:['src/main.jsx'],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',
  external:['react','react/jsx-runtime','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'},
  define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},
  plugins:[{name:'transport-fixtures',setup(b){
    b.onLoad({filter:/\/src\/main\.jsx$/},args=>({loader:'jsx',contents:readFileSync(args.path,'utf8').replace(/ReactDOM\.createRoot[\s\S]*$/, 'export default function Root(){return <><EmployeeProfileLiveEnhancer/><App/></>}')}))
    b.onResolve({filter:/\/(api|supabase)$/},args=>({path:args.path.split('/').at(-1),namespace:'fixture'}))
    b.onLoad({filter:/.*/,namespace:'fixture'},({path})=>({loader:'js',contents:path==='api'?
      'export const isApiConfigured=true; export const isReadConfigured=true; export const veraApi=globalThis.__navigationApi;':
      `export const isAuthConfigured=true;export const isSupabaseConfigured=false;export const supabase=null;
       export const getCurrentSession=async()=>({access_token:'synthetic',user:{id:'synthetic'}});
       export const refreshCurrentSession=getCurrentSession;
       export const onVeraAuthStateChange=()=>()=>{};export const signOutVera=async()=>{};export const signInWithVeraPassword=async()=>{};`
    }))
  }}],
})

test('actual application opens leave from Live Tour with production startup enhancers',async()=>{
  const dom=new JSDOM('<body><div id="root"></div></body>',{url:'https://example.test',pretendToBeVisual:true})
  const observers=[],errors=[], calls=[],day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh'}).format(new Date())
  let failStats=false
  const reasons=[{name:'Có phép',leave_type:'Có phép'},{name:'Đi trễ',leave_type:'Vi phạm'}]
  const api={
    me:async()=>({employee_username:'Test',role:'admin',is_active:true,permissions:{leave_create:true,leave_quota_check:true}}),
    notificationSettings:async()=>({settings:[]}),
    uiLayout:async()=>({revision:1,layout:{desktop:{},mobile:{}}}),
    leaveRecords:async(start,end)=>{calls.push(['records',start,end]);return {records:[{record_uid:'test',employee_name:'Test',leave_date:day,leave_reason:'Có phép',leave_type:'Có phép'}]}},
    leaveDailyStats:async()=>({days:[]}),leaveReasons:async()=>({reasons}),
    employees:async()=>({employees:[{username:'Test',employee_username:'Test',role:'nhanvien',employment_status:'Đang làm việc'}]}),
    watchDates:async()=>({watch_dates:[]}),
    leaveListStats:async()=>({summary:{total_leave:1,paid:1},monthly_allowances:failStats?[{month:null}]:[]}),
    leaveQuotaCheck:async()=>({start:day,end:day,limits:{days:5},items:[]}),
  }
  const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,
    localStorage:dom.window.localStorage,sessionStorage:dom.window.sessionStorage,
    getComputedStyle:dom.window.getComputedStyle.bind(dom.window),requestAnimationFrame:dom.window.requestAnimationFrame.bind(dom.window),cancelAnimationFrame:dom.window.cancelAnimationFrame.bind(dom.window),
    __navigationApi:new Proxy(api,{get:(target,key)=>target[key]|| (async()=>({}))}),
    IS_REACT_ACT_ENVIRONMENT:true,
    fetch:async(url)=>new Response(JSON.stringify(new URL(url).pathname.endsWith('/reason-types')?{items:reasons}:{leave_reasons:[reasons[0]],violations:[reasons[1]]}),{status:200,headers:{'Content-Type':'application/json'}}),
  }
  for(const key of ['MutationObserver','HTMLElement','Element','HTMLInputElement','HTMLSelectElement','HTMLTextAreaElement','Event','CustomEvent','MouseEvent','Node'])globals[key]=dom.window[key]
  globals.MutationObserver=class extends dom.window.MutationObserver {constructor(callback){super(callback);observers.push(this)}}
  const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
  for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true,writable:true})
  window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
  window.scrollTo=()=>{}
  window.fetch=globals.fetch
  window.addEventListener('error',event=>{errors.push(event.error);event.preventDefault()})
  const mod={exports:{}}
  class Boundary extends React.Component {
    state={failed:false};static getDerivedStateFromError(){return {failed:true}}
    componentDidCatch(error){errors.push(error)}
    render(){return this.state.failed?React.createElement('p',{role:'alert'},'Application crashed'):this.props.children}
  }
  const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
  const settle=async()=>{for(let i=0;i<4;i++)await act(async()=>{await new Promise(r=>setTimeout(r,80))})}
  const click=async(label)=>{
    const button=[...document.querySelectorAll('.sidebar a')].find(b=>b.textContent.trim()===label)
    assert.ok(button,`Menu ${label} exists`);await act(async()=>button.click());await settle()
  }
  try{
    new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports)
    await act(async()=>root.render(React.createElement(React.StrictMode,null,React.createElement(Boundary,null,React.createElement(mod.exports.default)))))
    await settle();assert.deepEqual(errors,[]);assert.ok(document.querySelector('.live-tour-workspace'))
    await click('Đăng ký nghỉ');assert.deepEqual(errors,[]);assert.ok(document.querySelector('.registration-panel .leave-form'))
    await click('Live Tour');await click('Đăng ký nghỉ');assert.deepEqual(errors,[])
    assert.equal(document.querySelectorAll('[data-leave-list-personal-stats]').length,1)
    assert.ok(calls.length>0)
    await click('Live Tour')
    failStats=true
    const originalError=console.error
    console.error=()=>{}
    try { await click('Đăng ký nghỉ') } finally {console.error=originalError}
    assert.ok(document.querySelector('.sidebar'), 'A page error must preserve navigation')
    assert.match(document.querySelector('.page-recovery').textContent,/Không mở được Đăng ký nghỉ/)
    const link=new URL(document.querySelector('.page-recovery a').href)
    assert.equal(link.searchParams.get('page'),'leave')
    assert.equal(link.searchParams.get('standalone'),'1')
    assert.ok(link.searchParams.get('reload'))
    failStats=false
    await act(async()=>document.querySelector('.page-recovery button').click());await settle()
    assert.ok(document.querySelector('.registration-panel .leave-form'))
    assert.equal(document.querySelector('.page-recovery'),null)
    await click('Live Tour');await click('Đăng ký nghỉ')
    assert.equal(document.querySelectorAll('[data-leave-list-personal-stats]').length,1)
    assert.ok(calls.every(([,start,end])=>start.slice(0,7)===end.slice(0,7)))
  }finally{
    await act(async()=>root.unmount());observers.forEach(o=>o.disconnect());dom.window.close()
    for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}
  }
})
