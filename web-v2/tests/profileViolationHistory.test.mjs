import test, { after } from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
const boot = new JSDOM('<body/>'); globalThis.window = boot.window; globalThis.document = boot.window.document
const built = await build({ entryPoints: ['src/pages/ProfilePage.jsx'], bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', loader: {'.css':'empty'}, define: {'import.meta.env':'{}'}, external: ['react','react-dom','react/jsx-runtime'], plugins: [{ name:'mock-profile-services', setup(b) {
 b.onResolve({filter:/\/lib\/api$/},()=>({path:'api',namespace:'mock'}))
 b.onResolve({filter:/\/lib\/pushNotifications$/},()=>({path:'push',namespace:'mock'}))
 b.onResolve({filter:/EmployeeIdentityPanel$/},()=>({path:'identity',namespace:'mock'}))
 b.onLoad({filter:/.*/,namespace:'mock'},args=>({contents: args.path==='identity' ? 'export default ()=>null;' : args.path==='api' ? `export const apiRequest=async path=>{window.historyReads.push(path);return {rows:[{id:'self',employee_username:'self',employee_name:'My Employee',violation_date:'2026-10-06',reason:'My violation',amount:10000}]}};export const veraApi={profile:async()=>({profile:{username:'self',birth_date:'',cccd_issue_date:''}}),profileReferenceData:async()=>({provinces:[],banks:[]})};` : `const state=()=>Promise.resolve({supported:false,subscribed:false});export const syncExistingPushSubscription=state,readPushState=state,enablePushNotifications=state,disablePushNotifications=state;`}))
} }] })
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
after(()=>boot.window.close())
for (const forcePasswordChange of [false,true]) test(`profile own history respects password gate (${forcePasswordChange})`,async t=>{
 const dom=new JSDOM('<div id="root"/>',{url:'https://example.test',pretendToBeVisual:true});globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 window.historyReads=[];window.HTMLDialogElement.prototype.close=function(){this.open=false}
 const {createRoot}=await import('react-dom/client'),root=createRoot(document.getElementById('root'));t.after(async()=>{await act(()=>root.unmount());dom.window.close()})
 await act(async()=>root.render(React.createElement(mod.exports.default,{user:{role:'support',employee_username:'self',permissions:{profile:true}},forcePasswordChange})))
 if(forcePasswordChange){assert.equal(window.historyReads.length,0);assert.equal(document.querySelector('.schedule-violations'),null)}
 else {assert.equal(window.historyReads.length,1);assert.match(window.historyReads[0],/^\/v2\/work-schedule\/violations\/me\?start=/);assert.match(document.querySelector('.schedule-violations').textContent,/My violation/)}
})
