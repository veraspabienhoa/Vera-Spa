import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built=await build({stdin:{contents:`import React,{act} from 'react';import{createRoot}from'react-dom/client';import Actions,{PagePermissionProvider}from'./src/components/PagePermissionActions';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=role=>act(async()=>root.render(<PagePermissionProvider user={{role}}><Actions page="training"/></PagePermissionProvider>));window.unmount=()=>act(async()=>root.unmount());`,resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'api',setup(b){b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}));b.onLoad({filter:/.*/,namespace:'mock'},()=>({contents:'export const veraApi={permissions:()=>window.api.read(),savePermissions:(...args)=>window.api.save(...args)}'}))}}]})
async function setup(role='admin'){
 const dom=new JSDOM('<div id="root"></div>',{url:'https://test.local',runScripts:'dangerously',pretendToBeVisual:true}),w=dom.window
 w.MessageChannel=class {constructor(){this.port1={};this.port2={postMessage:()=>setTimeout(()=>this.port1.onmessage?.(),0)}}}
 w.IS_REACT_ACT_ENVIRONMENT=true
 const data={scoped_permission_policy_version:1,revision:2,pages:[{id:'training',label:'Đào tạo',view_feature:'training_view',features:{training_view:'Xem đào tạo',training_session_create:'Nhập nhật ký'}},{id:'other',features:{profile:'Hồ sơ'}}],accounts:[{username:'An',full_name:'An Nguyễn',role:'nhanvien'},{username:'Binh',role:'nhanvien'},{username:'admin',role:'admin'}],defaults:{nhanvien:['profile','training_view']},dependencies:{training_session_create:['training_view']},account_overrides:{Binh:{training_view:false}},role_overrides:{}}
 const writes=[];w.api={read:async()=>structuredClone(data),save:async(...args)=>{writes.push(args);if(w.conflict)throw Error('Phân quyền đã thay đổi');data.revision++;data.account_overrides[args[1]]=Object.fromEntries(['profile','training_view','training_session_create'].map(k=>[k,args[2].allowed_features.includes(k)]));return{revision:data.revision,scoped_permission_policy_version:1}}}
 w.eval(built.outputFiles[0].text);await w.mount(role)
 return{w,dom,writes}
}
const click=async(w,text)=>{const b=[...w.document.querySelectorAll('button')].find(x=>x.textContent===text);assert.ok(b,text);await w.act(async()=>b.click())}
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
