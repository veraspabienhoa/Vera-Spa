import test from 'node:test'
import assert from 'node:assert/strict'
import {createRequire} from 'node:module'
import {act} from 'react'
import {readFile} from 'node:fs/promises'
import {build} from 'esbuild'
import {JSDOM} from 'jsdom'
const source=await readFile('src/lib/departmentSalaryAdvanceLedger.js','utf8')
const built=await build({stdin:{contents:source+'\nexport {ensurePanel,refreshLedger,applyAdvancesToPayrollRows}; export function seed(){currentPayload.employee_catalog=[{employee_username:"dat",employee_name:"Ngô Sĩ Đạt",department_label:"Lễ tân"}]}',resolveDir:process.cwd()+'/src/lib'},bundle:true,write:false,format:'cjs',platform:'node',jsx:'automatic',external:['react','react-dom','react-dom/client','react/jsx-runtime'],define:{'import.meta.env':'{"VITE_VERA_API_BASE_URL":"https://api.invalid"}'},plugins:[{name:'auth',setup(b){b.onResolve({filter:/supabase$/},()=>({path:'auth',namespace:'fixture'}));b.onLoad({filter:/.*/,namespace:'fixture'},()=>({contents:'export const getCurrentSession=async()=>null'}))}}]})
const bootstrap=new JSDOM('<body/>');globalThis.window=bootstrap.window;globalThis.document=bootstrap.window.document
const mod={exports:{}};new Function('require','module','exports',built.outputFiles[0].text)(createRequire(import.meta.url),mod,mod.exports)
test('hidden ledger and employee selection with pointer and keyboard focus',()=>{
 const dom=new JSDOM('<div class="department-payroll-page"><div class="department-payroll-panel"><div class="department-payroll-toolbar"></div></div></div>');globalThis.window=dom.window;globalThis.document=dom.window.document;globalThis.IS_REACT_ACT_ENVIRONMENT=true
 try {
 mod.exports.seed();let panel;act(()=>{panel=mod.exports.ensurePanel()});const content=panel.querySelector('[data-advance-content]'),toggle=panel.querySelector('[data-advance-toggle]');assert.equal(content.hidden,true);assert.equal(panel.querySelector('[data-advance-refresh]').previousElementSibling,toggle);assert.match(panel.querySelector('[data-advance-deduction-month]').value,/^\d{4}-\d{2}$/);assert.match(panel.querySelector('thead').textContent,/Tháng trừ lương/);toggle.click();assert.equal(content.hidden,false)
 const dateInput=panel.querySelector('[data-advance-date] input[type="text"]'),picker=panel.querySelector('[data-advance-date] input[type="date"]')
 assert.ok(panel.querySelector('.vera-date-picker-button'));assert.equal(dateInput.required,true)
 const change=(node,value,event='input')=>act(()=>{Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new window.Event(event,{bubbles:true}))})
 change(dateInput,'29022028');assert.equal(dateInput.value,'29-02-2028');assert.equal(dateInput.checkValidity(),true);assert.equal(picker.value,'2028-02-29')
 change(dateInput,'31022028');assert.equal(dateInput.checkValidity(),false)
 change(picker,'2026-10-06','change');assert.equal(dateInput.value,'06-10-2026');assert.equal(dateInput.checkValidity(),true)
 const input=panel.querySelector('[data-advance-employee]');input.focus();const option=panel.querySelector('[data-advance-employee-option]'),menu=option.parentElement
 const down=new window.Event('pointerdown',{bubbles:true,cancelable:true});option.dispatchEvent(down);assert.equal(down.defaultPrevented,true);option.focus();assert.equal(menu.hidden,false);option.click();assert.equal(input.dataset.selectedUsername,'dat');assert.match(input.value,/Ngô Sĩ Đạt/);assert.equal(menu.hidden,true)
 toggle.click();assert.equal(content.hidden,true);assert.equal(mod.exports.ensurePanel(),panel)
 } finally {act(()=>{document.querySelector('.department-payroll-page').remove();mod.exports.ensurePanel()});dom.window.close();delete globalThis.window;delete globalThis.document}
})


test('browsing another month preserves the payroll deduction',async()=>{
 const dom=new JSDOM('<div class="department-payroll-page"><div class="department-payroll-panel"><div class="department-payroll-toolbar"><input type="month" value="2026-09"></div></div></div>');globalThis.window=dom.window;globalThis.document=dom.window.document
 const originalFetch=globalThis.fetch,originalEvent=globalThis.CustomEvent,requests=[];globalThis.CustomEvent=dom.window.CustomEvent;globalThis.fetch=async url=>{const month=new URL(url).searchParams.get('month');requests.push(month);return new Response(JSON.stringify({items:[],employee_catalog:[],summary:{month,by_employee:{dat:month==='2026-09'?100:900}}}))}
 try{
 let panel;act(()=>{panel=mod.exports.ensurePanel()});const custom=panel.querySelector('[data-advance-filter-month]');custom.value='2026-08';panel.querySelector('[data-advance-period="custom"]').click();assert.equal(custom.hidden,false)
 let detail;window.addEventListener('vera-salary-advance-summary',event=>{detail=event.detail});await act(async()=>{await mod.exports.refreshLedger(true)});mod.exports.applyAdvancesToPayrollRows();assert.equal(detail.month,'2026-09');assert.equal(detail.byEmployee.dat,100);assert.ok(requests.includes('2026-08'));assert.ok(requests.includes('2026-09'))
 panel.querySelector('[data-advance-period="current"]').click();assert.equal(custom.hidden,true)
 }finally{await act(async()=>{await new Promise(resolve=>setTimeout(resolve,200))});act(()=>{document.querySelector('.department-payroll-page').remove();mod.exports.ensurePanel()});globalThis.fetch=originalFetch;globalThis.CustomEvent=originalEvent;dom.window.close();delete globalThis.window;delete globalThis.document}
})
