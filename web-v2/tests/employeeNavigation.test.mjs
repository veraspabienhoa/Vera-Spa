import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import { transformSync } from '@babel/core'
import layoutIdentity from '../build/layoutIdentity.js'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const require = createRequire(import.meta.url)
const built = await build({
  entryPoints:['src/main.jsx'],bundle:true,write:false,platform:'node',format:'cjs',jsx:'automatic',
  external:['react','react/jsx-runtime','react-dom','react-dom/client','lucide-react'],loader:{'.css':'empty'},
  define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},
  plugins:[{name:'transport-fixtures',setup(b){
    b.onLoad({filter:/\/src\/main\.jsx$/},args=>({loader:'jsx',contents:readFileSync(args.path,'utf8').replace(/ReactDOM\.createRoot[\s\S]*$/, 'export default function Root(){return <><EmployeeProfileLiveEnhancer/><App/></>}')}))
    b.onLoad({filter:/\.jsx$/},args=>({loader:'jsx',contents:transformSync(readFileSync(args.path,'utf8'),{filename:args.path,parserOpts:{plugins:['jsx']},plugins:[layoutIdentity],configFile:false,babelrc:false}).code}))
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

for (const entry of ['/?page=employees&standalone=1', '/']) test(`real employee page survives startup, refresh, filtering and navigation from ${entry}`, async () => {
  const dom = new JSDOM('<body><div id="root"></div></body>', {url:`https://example.test${entry}`,pretendToBeVisual:true})
  const errors=[], observers=[], requests=[]
  let releaseStaff, saveShouldFail=true, writes=0
  const staffReady = new Promise(resolve => { releaseStaff=resolve })
  const employees=[{username:'Ánh Mẫu',full_name:'Nguyễn Ánh Mẫu',role:'nhanvien',employment_status:'Đang làm việc',work_shift:'Ca 1'},
    {username:'Bình Mẫu',full_name:'Trần Bình Mẫu',role:'letan',employment_status:'Đang làm việc',work_shift:'Ca 2',profile_requirement_exempt:true},
    {username:'Chi Mẫu',full_name:'Trần Chi Mẫu',role:'nhanvien',employment_status:'Đang làm việc',birth_date:'01/01/2000',gender:'Nữ',ethnicity:'Kinh',phone:'0900000000',email:'chi@example.invalid',province:'Tỉnh mẫu',ward:'Phường mẫu',address_detail:'Địa chỉ mẫu',bank_account:'000000',bank_name:'Ngân hàng mẫu',cccd_number:'000000000000',cccd_issue_date:'01/01/2025',cccd_issue_place:'Bộ Công an'}]
  const permissions={employee_view:true,employee_edit_save:true,staff_export:true,employee_face_id_view:true,employee_face_id_manage:true}
  const payload=()=>({employees:employees.map(e=>({...e})),permissions,summary:{total:3,active:3},role_options:['nhanvien','letan'],
    status_options:['Đang làm việc'],cycle_options:[],shifts_by_department:{'Nhân viên + Leader':['Ca 1','Ca 2']}})
  const api={
    me:async()=>({employee_username:'Test',role:'admin',is_active:true,permissions}),
    notificationSettings:async()=>({settings:[]}),uiLayout:async()=>({revision:1,layout:{desktop:{},mobile:{}}}),
    staff:async()=>{requests.push('staff');await staffReady;return payload()},
    employees:async()=>({employees}),profileReferenceData:async()=>({provinces:[],wards:[],banks:[]}),
    updateStaff:async(username, changes)=>{
      writes++
      if(saveShouldFail)throw Error('Simulated save failure')
      const employee=employees.find(row=>row.username===username)
      Object.assign(employee,changes)
      return {employee:{...employee}}
    },
  }
  const fetchFixture=async url=>new Response(JSON.stringify(String(url).includes('/face-id/self-update-settings')
    ? {enabled:true,individual:{},missing:['Ánh Mẫu']} : {provinces:[],wards:[],banks:[],items:[],can_manage:true,photo:null}),
    {status:200,headers:{'Content-Type':'application/json'}})
  const globals={window:dom.window,document:dom.window.document,navigator:dom.window.navigator,
    localStorage:dom.window.localStorage,sessionStorage:dom.window.sessionStorage,
    getComputedStyle:dom.window.getComputedStyle.bind(dom.window),requestAnimationFrame:dom.window.requestAnimationFrame.bind(dom.window),cancelAnimationFrame:dom.window.cancelAnimationFrame.bind(dom.window),
    __navigationApi:new Proxy(api,{get:(target,key)=>target[key]|| (async()=>({}))}),
    IS_REACT_ACT_ENVIRONMENT:true,fetch:fetchFixture}
  for(const key of ['MutationObserver','HTMLElement','Element','HTMLInputElement','HTMLSelectElement','HTMLTextAreaElement','Event','CustomEvent','MouseEvent','Node'])globals[key]=dom.window[key]
  globals.MutationObserver=class extends dom.window.MutationObserver {constructor(callback){super(callback);observers.push(this)}}
  const saved=Object.fromEntries(Object.keys(globals).map(k=>[k,Object.getOwnPropertyDescriptor(globalThis,k)]))
  for(const[k,v]of Object.entries(globals))Object.defineProperty(globalThis,k,{value:v,configurable:true,writable:true})
  window.matchMedia=()=>({matches:false,addEventListener(){},removeEventListener(){}})
  window.scrollTo=()=>{};window.fetch=fetchFixture
  window.addEventListener('error',event=>{errors.push(String(event.error?.stack||event.error));event.preventDefault()})
  const oldError=console.error;console.error=(...args)=>{errors.push(args.map(x=>String(x?.stack||x)).join(' '))}
  const mod={exports:{}}
  const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'))
  const settle=async(count=5)=>{for(let i=0;i<count;i++)await act(async()=>{await new Promise(r=>setTimeout(r,60))})}
  const navigate=async label=>{
    const toggle=document.querySelector('.standalone-menu-toggle[aria-expanded="false"]')
    if(toggle)await act(async()=>toggle.click())
    const link=[...document.querySelectorAll('.sidebar a')].find(b=>b.textContent.trim()===label)
    assert.ok(link,`Menu ${label} exists`);await act(async()=>link.click());await settle()
  }
  const assertOpen=()=>{
    assert.equal(Boolean(document.querySelector('.page-recovery')),false,errors.join('\n'))
    assert.ok(document.querySelector('.staff-page'),errors.join('\n'))
    assert.deepEqual(errors.filter(x=>!x.includes('not wrapped in act')),[])
  }
  const filter=async value=>{
    const input=document.querySelector('.staff-list-search input')
    await act(async()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(input,value);input.dispatchEvent(new Event('input',{bubbles:true}))})
    await settle();assertOpen()
  }
  const assertSummary=(total,incomplete)=>assert.equal(document.querySelector('.staff-list-panel .panel-title-row p').textContent,
    `${total} nhân viên phù hợp bộ lọc.${incomplete ? ` · ${incomplete} hồ sơ chưa đầy đủ (dòng vàng).` : ''}`)
  try {
    new Function('require','module','exports',built.outputFiles[0].text)(require,mod,mod.exports)
    await act(async()=>root.render(React.createElement(React.StrictMode,null,React.createElement(mod.exports.default))))
    await settle()
    if(entry==='/')await navigate('Nhân viên')
    await act(async()=>releaseStaff());await settle();assertOpen()
    assert.equal(document.querySelectorAll('.staff-table tbody tr').length,3)
    assertSummary(3,1)
    for(const selector of ['.staff-table', '.staff-mobile-list']) {
      const badges=document.querySelectorAll(`${selector} .staff-incomplete-badge`)
      assert.equal(badges.length,1)
      assert.match(badges[0].textContent,/Thiếu: Ngày sinh/)
      assert.doesNotMatch(badges[0].textContent,/Quận\/Huyện/)
    }
    const input=document.querySelector('.staff-list-search input')
    await filter('Ánh Mẫu');assert.equal(document.querySelectorAll('.staff-table tbody tr').length,1);assertSummary(1,1)
    await act(async()=>document.querySelector('.staff-list-panel .panel-title-row button').click())
    await settle();assertOpen();assert.equal(input.value,'Ánh Mẫu')
    await filter('Không có nhân viên này');assert.equal(document.querySelectorAll('.staff-table tbody tr').length,0);assertSummary(0,0)
    await filter('');assert.equal(document.querySelectorAll('.staff-table tbody tr').length,3);assertSummary(3,1)
    await filter('Bình Mẫu');assertSummary(1,0)
    await filter('Ánh Mẫu');assertSummary(1,1)
    await filter('Chi Mẫu');assertSummary(1,0)
    await navigate('Live Tour');await navigate('Nhân viên');assertOpen()
    assert.equal(writes,0,'opening and filtering must not save staff')
    assert.equal(document.querySelectorAll('.staff-face-actions button').length,3)
    assert.equal(document.querySelectorAll('.staff-toolbar select').length,4)
    await act(async()=>document.querySelector('.staff-table input[aria-label="Không tính lương Ánh Mẫu"]').click())
    await navigate('Live Tour')
    assertOpen()
    const dialog=()=>document.querySelector('.employee-navigation-dialog')
    const action=(label)=>[...dialog().querySelectorAll('button')].find(button=>button.textContent.trim()===label)
    assert.ok(dialog())
    await act(async()=>action('Tiếp tục chỉnh sửa').click())
    assertOpen()
    await navigate('Live Tour')
    await act(async()=>action('Lưu và chuyển').click())
    await settle()
    assert.ok(dialog(),'a failed save keeps the operator on Employees')
    assertOpen()
    assert.match(dialog().textContent,/Chưa lưu được toàn bộ dữ liệu/)
    saveShouldFail=false
    await act(async()=>action('Lưu và chuyển').click())
    await settle()
    assert.equal(document.querySelector('.staff-page'),null)
    assert.equal(employees[0].payroll_excluded,true)
    await navigate('Nhân viên');assertOpen()
    await act(async()=>document.querySelector('.staff-table input[aria-label="Không tính lương Ánh Mẫu"]').click())
    await navigate('Live Tour')
    assert.ok(dialog())
    await act(async()=>action('Không lưu').click())
    await settle()
    assert.equal(document.querySelector('.staff-page'),null)
    assert.equal(employees[0].payroll_excluded,true,'discarding edits preserves the stored value')
    await navigate('Nhân viên');assertOpen()
    await act(async()=>document.querySelector('.staff-table .staff-edit-button').click())
    const fullName=[...document.querySelectorAll('.employee-profile-modal-panel label')]
      .find(label=>label.textContent.includes('Họ và tên đầy đủ')).querySelector('input')
    await act(async()=>{
      Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(fullName,'Tên đang sửa')
      fullName.dispatchEvent(new Event('input',{bubbles:true}))
    })
    await navigate('Live Tour')
    assert.ok(dialog(),'the profile editor also guards menu navigation')
    await act(async()=>action('Không lưu').click())
    await settle()
    assert.equal(employees[0].full_name,'Nguyễn Ánh Mẫu')
    await navigate('Nhân viên');assertOpen()
    assert.ok(requests.length>0)
  } finally {
    releaseStaff()
    try { await act(async()=>root.unmount()) } finally {
      observers.forEach(o=>o.disconnect());dom.window.close();console.error=oldError
      for(const[k,v]of Object.entries(saved)){if(v)Object.defineProperty(globalThis,k,v);else delete globalThis[k]}
    }
  }
})
