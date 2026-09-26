import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const require = createRequire(import.meta.url)
const built = await build({
  stdin: { contents: `
    import React from 'react';
    import Page from './src/pages/LeaveRegistrationPage';
    import Enhancements from './src/pages/LeaveRegistrationEnhancements';
    import Stats from './src/pages/LeaveListPersonalStats';
    import Types from './src/pages/LeaveListTypeColumn';
    export default function Route({user}) { return <><Page user={user}/><Enhancements user={user}/><Stats user={user}/><Types user={user}/></> }
  `, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react','react/jsx-runtime','react-dom','lucide-react'], loader: { '.css':'empty' },
  define: { 'import.meta.env.VITE_VERA_API_BASE_URL': '"https://api.invalid"' },
  plugins: [{name:'api-boundaries',setup(b){
    b.onResolve({filter:/\/lib\/(api|data|watchBell|pushNotifications|supabase)$/},args=>({path:args.path.split('/').at(-1),namespace:'fixture'}))
    b.onLoad({filter:/.*/,namespace:'fixture'},({path})=>({loader:'js',contents:{
      api:'export const isApiConfigured=true; export const veraApi=globalThis.__leaveRouteApi;',
      data:'export const loadEmployees=async()=>[];export const loadLeaveDailyStats=async()=>[];export const loadLeaveReasons=async()=>[];export const loadLeaveRecords=async()=>[];',
      watchBell:'export const playWatchBellSound=async()=>true;export const unlockWatchBellAudio=async()=>true;',
      pushNotifications:'export const disablePushNotifications=async()=>({});export const enablePushNotifications=async()=>({});export const readPushState=async()=>({});export const syncExistingPushSubscription=async()=>({});',
      supabase:'export const getCurrentSession=async()=>({access_token:"synthetic"});',
    }[path]}))
  }}],
})
async function fixture(role, failRecords=false) {
  const dom=new JSDOM('<body><div id="root"></div></body>',{url:'https://example.test',pretendToBeVisual:true})
  const errors=[], calls=[]
  const day=new Intl.DateTimeFormat('en-CA',{timeZone:'Asia/Ho_Chi_Minh'}).format(new Date())
  const catalog=[{name:'Có phép',leave_type:'Có phép'}]
  const values={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,
    MutationObserver:dom.window.MutationObserver,HTMLElement:dom.window.HTMLElement,
    HTMLInputElement:dom.window.HTMLInputElement,HTMLSelectElement:dom.window.HTMLSelectElement,HTMLTextAreaElement:dom.window.HTMLTextAreaElement,
    IS_REACT_ACT_ENVIRONMENT:true,
    fetch:async(url)=>({ok:true,json:async()=>new URL(url).pathname.endsWith('/reason-types')?{items:catalog}:{leave_reasons:catalog,violations:[]}}),
    __leaveRouteApi:{
      leaveRecords:async(start,end)=>{calls.push(['records',start,end]);if(failRecords)throw Error('Lỗi đọc thử nghiệm');return {records:[{record_uid:'synthetic',employee_name:'An An',leave_date:day,leave_reason:'Có phép',leave_type:'Có phép'}]}},
      leaveDailyStats:async()=>({days:[]}),leaveReasons:async()=>({reasons:catalog}),
      employees:async()=>({employees:[{username:'An An',employee_username:'An An',role:'nhanvien',employment_status:'Đang làm việc'}]}),
      watchDates:async()=>({watch_dates:[]}),notificationSettings:async()=>({settings:[]}),
      leaveListStats:async(start,end)=>{calls.push(['stats',start,end]);return {summary:{total_leave:1,paid:1},monthly_allowances:[]}},
      leaveQuotaCheck:async(start,end)=>{calls.push(['quota',start,end]);return {start,end,limits:{days:5},items:[]}},
    },
  }
  const descriptors=Object.fromEntries(Object.keys(values).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
  for(const [key,value]of Object.entries(values))Object.defineProperty(globalThis,key,{value,configurable:true,writable:true})
  const module={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(require,module,module.exports)
  class Boundary extends React.Component {
    state={failed:false}
    static getDerivedStateFromError(){return {failed:true}}
    componentDidCatch(error){errors.push(error)}
    render(){return this.state.failed?React.createElement('p',{role:'alert'},'Route crashed'):this.props.children}
  }
  const {createRoot}=await import('react-dom/client')
  const root=createRoot(dom.window.document.querySelector('#root'))
  const user={role,employee_username:'An An',permissions:{leave_quota_check:role==='admin',leave_create:true}}
  const render=async(show=true)=>{await act(async()=>root.render(React.createElement(React.StrictMode,null,React.createElement(Boundary,null,show?React.createElement(module.exports.default,{user}):React.createElement('p',null,'Other page')))));await act(async()=>{await new Promise(r=>setTimeout(r,100))})}
  const originalError=console.error
  console.error=(...args)=>{if(!String(args[0]).includes('above error occurred'))originalError(...args)}
  try { await render() } catch(error){errors.push(error)}
  return {doc:dom.window.document,errors,calls,render,day,
    async close(){await act(()=>root.unmount());dom.window.close();console.error=originalError;for(const[k,d]of Object.entries(descriptors)){if(d)Object.defineProperty(globalThis,k,d);else delete globalThis[k]}}
  }
}
for(const role of ['admin','letan','nhanvien'])test(`complete leave route opens and reopens with all enhancements: ${role}`,async()=>{
  const f=await fixture(role)
  try {
    assert.deepEqual(f.errors.map(e=>`${e.name}: ${e.message}`),[])
    assert.ok(f.doc.querySelector('.leave-form'))
    assert.ok(f.doc.querySelector('.stable-data-region .leave-list-wrap'))
    assert.equal(f.doc.querySelectorAll('[data-leave-list-personal-stats]').length,1)
    assert.ok(f.doc.querySelector('.leave-list-personal-summary'))
    if(role==='admin'){
      await act(async()=>f.doc.querySelector('.leave-quota-check-button').click())
      assert.deepEqual(f.calls.find(c=>c[0]==='quota'),['quota',f.day,f.day])
    }else assert.equal(f.doc.querySelector('.leave-quota-check-button'),null)
    await f.render(false);await f.render(true)
    assert.deepEqual(f.errors,[])
    assert.equal(f.doc.querySelectorAll('[data-leave-list-personal-stats]').length,1)
    assert.ok(f.doc.querySelector('.leave-form'))
    for(const[,start,end]of f.calls)assert.equal(start.slice(0,7),end.slice(0,7))
  }finally{await f.close()}
})
test('record read failure keeps the complete leave form and statistics mounted',async()=>{
  const f=await fixture('admin',true)
  try {assert.deepEqual(f.errors,[]);assert.ok(f.doc.querySelector('.leave-form'));assert.ok(f.doc.querySelector('.leave-list-personal-summary'));assert.match(f.doc.body.textContent,/Lỗi đọc thử nghiệm/)}
  finally{await f.close()}
})
