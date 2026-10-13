import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built=await build({stdin:{contents:`import React,{act} from 'react';import{createRoot}from'react-dom/client';import Actions,{PagePermissionProvider}from'./src/components/PagePermissionActions';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=(role,props={})=>act(async()=>root.render(<PagePermissionProvider user={{role}}><Actions page="training" {...props}/></PagePermissionProvider>));window.mountManaged=(page,tab='Hiện tại',role='admin')=>act(async()=>root.render(<PagePermissionProvider user={{role}} page={page}><main><Actions primary page={page}/><h1>{page}</h1><section><Actions page="reports" label={tab}/></section></main></PagePermissionProvider>));window.unmount=()=>act(async()=>root.unmount());`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const veraApi={permissions:()=>window.api.read(),savePermissions:(...args)=>window.api.save(...args)}'}))}}]})
async function setup(role='admin'){
 const dom=new JSDOM('<div id="root"></div>',{url:'https://test.local',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window
 w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 w.IS_REACT_ACT_ENVIRONMENT=true
 const data={scoped_permission_policy_version:1,revision:2,pages:[{id:'training',label:'Đào tạo',view_feature:'training_view',features:{training_view:'Xem đào tạo',training_session_create:'Nhập nhật ký'}},{id:'other',features:{profile:'Hồ sơ'}}],accounts:[{username:'An',full_name:'An Nguyễn',role:'nhanvien'},{username:'Binh',role:'nhanvien'},{username:'admin',role:'admin'}],defaults:{nhanvien:['profile','training_view']},dependencies:{training_session_create:['training_view']},account_overrides:{Binh:{training_view:false}},role_overrides:{}}
 const writes=[];w.api={read:async()=>structuredClone(data),save:async(...args)=>{writes.push(args);if(w.conflict)throw Error('Phân quyền đã thay đổi');data.revision++;data.account_overrides[args[1]]=Object.fromEntries(data.pages.flatMap(page=>Object.keys(page.features)).map(k=>[k,args[2].allowed_features.includes(k)]));return{revision:data.revision,scoped_permission_policy_version:1}}}
 w.eval(built.outputFiles[0].text);await w.mount(role)
 return{w,dom,writes,data}
}
const click=async(w,text)=>{
 if (!w.document.querySelector('[role=dialog]')) { const launch=w.document.querySelector('.page-permission-launcher'); if(launch) await w.act(async()=>launch.click()) }
 const wanted=text==='Phân quyền'?'Phân quyền trang':text
 const b=[...w.document.querySelectorAll('[role=dialog] button')].find(x=>x.textContent===wanted);assert.ok(b,text);await w.act(async()=>b.click())
}
async function close(w){await w.unmount();w.close()}
test('non-admin cannot see or load contextual permission controls',async()=>{const{w}=await setup('letan');try{assert.equal(w.document.querySelector('button'),null)}finally{await close(w)}})
test('list includes role inheritance and excludes explicit denial',async()=>{const{w}=await setup();try{await click(w,'Tài khoản đã được phân quyền');const list=w.document.querySelector('.permission-account-results');assert.match(list.textContent,/An/);assert.match(list.textContent,/Kế thừa nhóm/);assert.doesNotMatch(list.textContent,/Binh/);assert.match(list.textContent,/admin/)}finally{await close(w)}})
test('scoped account save preserves unrelated permissions and checks revision',async()=>{const{w,writes}=await setup();try{
 await click(w,'Phân quyền');await w.act(async()=>w.document.querySelector('.permission-account-results button').click())
 const checks=w.document.querySelectorAll('fieldset input');assert.equal(checks.length,2)
 await w.act(async()=>checks[1].click());await click(w,'Lưu phân quyền')
 assert.equal(writes[0][0],'account');assert.equal(writes[0][1],'An');assert.equal(writes[0][2].expected_revision,2)
 assert.deepEqual([...writes[0][2].allowed_features].sort(),['profile','training_session_create','training_view'])
 assert.equal(writes[0][2].preserve_unchanged,true)
 assert.match(w.document.body.textContent,/Đã lưu phân quyền/)
}finally{await close(w)}})
test('conflict remains in modal and never claims success',async()=>{const{w}=await setup();try{await click(w,'Phân quyền');await w.act(async()=>w.document.querySelector('.permission-account-results button').click());w.conflict=true;await w.act(async()=>w.document.querySelectorAll('fieldset input')[1].click());await click(w,'Lưu phân quyền');assert.match(w.document.querySelector('[role=alert]').textContent,/đã thay đổi/);assert.doesNotMatch(w.document.body.textContent,/Đã lưu phân quyền/)}finally{await close(w)}})

test('performance tab permits scoped grant to a non-admin and lists the granted account',async()=>{
 const {w,writes,data}=await setup()
 try {
  data.pages.push({id:'reports',label:'Báo cáo',view_feature:'live_tour_reports_view',features:{live_tour_view:'Live Tour',live_tour_reports_view:'Xem báo cáo',live_tour_performance_view:'Xem tab Thời gian thực hiện'}})
  data.dependencies.live_tour_performance_view=['live_tour_reports_view'];data.dependencies.live_tour_reports_view=['live_tour_view']
  await w.mount('admin',{page:'reports',label:'Thời gian thực hiện',features:['live_tour_performance_view'],viewFeatures:['live_tour_performance_view']})
  await click(w,'Phân quyền · Thời gian thực hiện')
  await w.act(async()=>w.document.querySelector('.permission-account-results button').click())
  assert.equal(w.document.querySelector('fieldset').disabled,false)
  assert.equal(w.document.querySelectorAll('fieldset input').length,1)
  await w.act(async()=>w.document.querySelector('fieldset input').click());await click(w,'Lưu phân quyền')
  assert.ok(writes[0][2].allowed_features.includes('live_tour_performance_view'))
  assert.ok(writes[0][2].allowed_features.includes('live_tour_reports_view'))
  assert.ok(writes[0][2].allowed_features.includes('live_tour_view'))
  assert.match(w.document.body.textContent,/Đã lưu phân quyền/)
  await click(w,'Đóng');await click(w,'Tài khoản đã được phân quyền · Thời gian thực hiện')
  assert.match(w.document.querySelector('.permission-account-results').textContent,/An/)
  assert.doesNotMatch(w.document.querySelector('.permission-account-results').textContent,/Binh/)
 }finally{await close(w)}
})

test('managed page shows exactly one title launcher and moves page/tab actions into modal',async()=>{
 const{w}=await setup()
 try{
  await w.mountManaged('reports','Thời gian thực hiện')
  assert.equal(w.document.querySelectorAll('button').length,1)
  assert.equal(w.document.querySelector('h1 button')?.textContent,'Phân quyền')
  assert.equal(w.document.querySelector('[role=dialog]'),null)
  await w.act(async()=>w.document.querySelector('h1 button').click())
  assert.match(w.document.querySelector('[role=dialog]').textContent,/Phân quyền trang/)
  assert.match(w.document.querySelector('[role=dialog]').textContent,/Phân quyền · Thời gian thực hiện/)
  assert.match(w.document.querySelector('[role=dialog]').textContent,/Tài khoản đã được phân quyền/)
  await click(w,'Đóng')
  await w.mountManaged('reports','Doanh thu')
  assert.equal(w.document.querySelectorAll('button').length,1)
  await w.act(async()=>w.document.querySelector('h1 button').click())
  assert.match(w.document.querySelector('[role=dialog]').textContent,/Phân quyền · Doanh thu/)
  assert.doesNotMatch(w.document.querySelector('[role=dialog]').textContent,/Thời gian thực hiện/)
  await w.mountManaged('training')
  assert.equal(w.document.querySelector('[role=dialog]'),null)
  assert.equal(w.document.querySelectorAll('h1 button').length,1)
  await w.mountManaged('live-tour')
  assert.equal(w.document.querySelector('button'),null)
  assert.equal(w.document.querySelector('[role=dialog]'),null)
  await w.mountManaged('reports','Hiện tại','letan')
  assert.equal(w.document.querySelector('button'),null)
 }finally{await close(w)}
})
