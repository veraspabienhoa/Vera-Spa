import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/QuangNgaiPage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  define: { 'import.meta.env.VITE_VERA_API_BASE_URL': '"https://api.invalid"' },
  plugins: [{ name: 'revenue-fixture', setup(b) {
    b.onResolve({ filter: /(?:\/supabase|\/UiCustomText|\/UiToolbar|\/usePageRefresh)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ loader: 'js', contents:
      args.path === 'supabase' ? 'export const getCurrentSession=async()=>({access_token:"synthetic"}); export const isSupabaseConfigured=false; export const refreshCurrentSession=async()=>null; export const supabase=null;' :
      args.path === 'UiCustomText' ? 'export default function Text({children}){return children}' :
      args.path === 'usePageRefresh' ? 'export default function Hook(){}' :
      'import React from "react"; export default function Toolbar({children,...props}){return React.createElement("div",props,children)}',
    }))
  } }],
})

async function fixture(role, initial = 'manual', legacy = false, rowCount = 1, savedEnd = '2026-09-26', unified = false, savedStart = '2026-09-16', ledgerFixture = null) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
  let source = initial, revision = 0, hold = false, pending = null, today = '2026-09-26', dataRevision = 1
  const calls = []
  const names = ['window','document','navigator','ResizeObserver','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT','fetch','Date']
  const descriptors = Object.fromEntries(names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  const response = result => ({ ok: true, json: async () => result })
  const OriginalDate = globalThis.Date
  class FixtureDate extends OriginalDate {
    constructor(...args) { super(...(args.length ? args : [`${today}T12:00:00+07:00`])) }
    static now() { return new OriginalDate(`${today}T12:00:00+07:00`).getTime() }
  }
  const values = {
    Date: FixtureDate,
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    ResizeObserver: class { observe(){} disconnect(){} }, requestAnimationFrame: callback => setTimeout(callback, 0), cancelAnimationFrame: clearTimeout,
    IS_REACT_ACT_ENVIRONMENT: true,
    fetch: async (url, options = {}) => {
      const path = new URL(url).pathname, method = options.method || 'GET'
      calls.push({ path, method, body: options.body ? JSON.parse(options.body) : null, url })
      if (path.endsWith('/source')) {
        if (legacy) return { ok:false, status:404, json:async()=>({detail:'Not Found'}) }
        if (method === 'PUT') { source = JSON.parse(options.body).source; revision += 1 }
        return response({ source, revision, period_report_version: Number(unified) })
      }
      if (path.endsWith('/revision')) return response({revision:`fixture-${revision}-${dataRevision}-${today}`})
      const cutoff = new URL(url).searchParams.get('end')
      const filtered = cutoff === '2026-09-24'
      if (path.endsWith('/period-report') || path.endsWith('/report-period')) {
        const body=options.body ? JSON.parse(options.body) : null
        const selectedEnd=body?.end_date || cutoff || savedEnd
        const selectedStart=body?.start_date || new URL(url).searchParams.get('start') || savedStart
        const historical=selectedEnd==='2026-09-24', tip=selectedStart==='2026-09-25' && selectedEnd==='2026-09-25'?15450000:historical?20:40
        const result={ok:true,default_period:!body && !cutoff,report_version:1,report_basis:'shared_history_and_system',source,source_revision:revision,
          total_income:historical?1000:1760,total_expense:historical?100:190.25,net_income:historical?900:1569.75,
          total_revenue:historical?1000:1760,period_tip:tip,balance:historical?880:1529.75,
          start_date:'2025-09-05',start_date_label:'05-09-2025',end_date:selectedEnd,business_date:'2026-09-26',
          current_date:'2026-09-26',current_date_label:'26-09-2026',period_tip_start:selectedStart,period_tip_end:selectedEnd,
          can_edit_tip:true,can_create_entry:source!=='auto',can_edit_entry:source!=='auto',can_delete_entry:source!=='auto'}
        if(body) savedEnd=body.end_date
        if(hold && !body){hold=false;return await new Promise(resolve=>{pending=()=>resolve(response(result))})}
        return response(result)
      }
      if (path.endsWith('/summary')) return response({ source, source_revision: legacy ? undefined : revision,
        total_income: filtered ? 1000 : 1760, total_expense: filtered ? 100 : 190.25, net_income: filtered ? 900 : 1569.75, period_tip: 20, balance: filtered ? 880 : 1549.75,
        end_date: cutoff || '2026-09-26', business_date: '2026-09-26',
        start_date: '2025-09-05', start_date_label: '05-09-2025', current_date: '2026-09-26', current_date_label: '26-09-2026',
        period_tip_start: '2026-09-16', period_tip_end: savedEnd,
        can_edit_tip: true, can_create_entry: source !== 'auto', can_edit_entry: source !== 'auto', can_delete_entry: source !== 'auto',
      })
      if (path === '/v2/quang-ngai/purchases') return response({rows:Array.from({length:rowCount},(_,i)=>({id:i,purchase_date:'2026-09-26',item:`Hàng ${i+1}`,amount:10,note:'Nguoi dat',entered_by:'Nguoi nhap',quantity:1,unit_price:10})), permissions:{}})
      if (path.endsWith('/purchases')) return response({ start_date:'2025-09-05', end_date:'2026-09-26', purchase_rows:Array.from({length:rowCount},(_,i)=>({id:i,date:'2026-09-26',date_label:'26-09-2026',item:`Hàng ${i+1}`,amount:10,buyer:'Nguoi dat',user:'Nguoi nhap'})) })
      if (path.endsWith('/purchase-reconcile')) {
        const params=new URL(url).searchParams, canonical=params.get('canonical')==='true'
        let start=params.get('start') || '2025-09-05'
        let end=params.get('end') || today
        const live=params.get('live_ledger')==='true'
        if(live && params.get('preset')==='all' && ledgerFixture?.length){
          start=ledgerFixture.map(row=>row.date).sort()[0]
          end=[today,...ledgerFixture.map(row=>row.date)].sort().at(-1)
        }
        if(!live && canonical && params.get('report_end') && params.get('report_end')<end) end=params.get('report_end')
        return response({canonical,live_ledger:live,source:legacy ? undefined : source,source_revision:legacy ? undefined : revision,
          start_date:start,end_date:end,purchase_rows:Array.from({length:rowCount},(_,i)=>({id:`purchase-${i}`,date:'2025-09-05',item:`Hàng ${i+1}`,amount:10})),
          ledger_rows:ledgerFixture ? ledgerFixture.filter(row=>row.date>=start && row.date<=end) : Array.from({length:rowCount},(_,i)=>({id:`auto:${i}`,date:'2025-09-05',date_label:'05-09-2025',type:'Thu',amount:1760,note:`Thu Quảng Ngãi ${i+1}`,read_only:source==='auto'})),
        })
      }
      if (path.endsWith('/audit')) return response({rows:[]})
      if (path.endsWith('/duplicates')) return response({groups:[]})
      if (path.endsWith('/ledger/export.xlsx')) return {ok:true,blob:async()=>new Blob(['synthetic full export'])}
      if (path.endsWith('/live-tour/reports')) return response({reports:[{business_date:'2026-09-20',tip:20}]})
      if (path === '/v2/quang-ngai/entry') return response({message:'Đã lưu Thu Chi'})
      if (path.endsWith('/tip-summary')) return response({ source, period_tip: 20 })
      if (path.endsWith('/tip-period')) { const body=JSON.parse(options.body); savedEnd=body.end_date; return response({ period_tip:20, balance:1549.75, period_tip_start:body.start_date, period_tip_end:body.end_date }) }
      throw new Error(`Unexpected request ${path}`)
    },
  }
  for (const [key,value] of Object.entries(values)) Object.defineProperty(globalThis, key, { value, configurable:true, writable:true })
  const module = { exports:{} }
  new Function('require','module','exports',built.outputFiles[0].text)(require,module,module.exports)
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(dom.window.document.querySelector('#root'))
  await act(async () => root.render(React.createElement(module.exports.default,{ user:{ role } })))
  await act(async () => { await new Promise(resolve => setTimeout(resolve, 300)) })
  return { doc:dom.window.document, calls, holdNextReport(){hold=true}, releaseReport(){pending?.()},
    async change(node,value) { await act(async()=>{Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype,'value').set.call(node,value);node.dispatchEvent(new dom.window.Event('input',{bubbles:true}));node.dispatchEvent(new dom.window.Event('change',{bubbles:true}))}) },
    button(text) { return [...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.includes(text)) },
    async externalMode(mode) { source=mode; revision+=1; await act(async()=>dom.window.dispatchEvent(new dom.window.Event('focus'))); await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))}) },
    async updateLedger(rows, day = today) { ledgerFixture=rows; today=day; dataRevision+=1; await act(async()=>dom.window.document.dispatchEvent(new dom.window.Event('visibilitychange'))); await act(async()=>{await new Promise(resolve=>setTimeout(resolve,320))}) },
    async close() { await act(async()=>root.unmount()); dom.window.close(); for(const [key,desc] of Object.entries(descriptors)){ if(desc) Object.defineProperty(globalThis,key,desc); else delete globalThis[key] } },
  }
}


for (const role of ['admin','giamdoc']) test(`${role}: independent ledger, entry form and retained tabs without TIP`, async()=>{
 const f=await fixture(role)
 try {
  assert.equal(f.doc.querySelector('h1').textContent,'Quảng Ngãi')
  assert.equal(f.doc.querySelector('.revenue-source-toggle'),null)
  assert.equal(f.doc.querySelector('.revenue-tip-editor'),null)
  assert.equal(f.doc.querySelectorAll('.revenue-card').length,3)
  assert.ok(f.button('Import thêm mới'));assert.ok(f.button('Import thay toàn bộ'))
  await act(async()=>f.button('Nhập doanh thu - chi phí').click())
  assert.ok(f.doc.querySelector('.revenue-entry-form'))
  for (const input of f.doc.querySelectorAll('.entry-note input')) { assert.equal(input.value,''); assert.equal(input.placeholder,'') }
  await f.change(f.doc.querySelector('.entry-amount input'),'123000')
  await act(async()=>f.doc.querySelector('.revenue-entry-form').dispatchEvent(new window.Event('submit',{bubbles:true,cancelable:true})))
  assert.ok(f.calls.some(c=>c.path==='/v2/quang-ngai/entry' && c.method==='POST' && c.body.income_amount===123000))
  for (const label of ['Lịch sử sửa, xóa','Kiểm tra dữ liệu trùng']) await act(async()=>f.button(label).click())
  assert.equal(f.button('Báo cáo mua hàng'),undefined)
  assert.equal(f.button('Tổng quan'),undefined)
  assert.ok(f.calls.some(c=>c.path==='/v2/quang-ngai/audit'))
  assert.ok(f.calls.some(c=>c.path==='/v2/quang-ngai/duplicates'))
  assert.ok(f.calls.every(c=>c.path.startsWith('/v2/quang-ngai/')))
  assert.ok(!f.calls.some(c=>/tip|live-tour|source|period-report/.test(c.path)))
 } finally {await f.close()}
})
for (const role of ['quanly','letan','locker','nhanvien']) test(`${role}: cannot open Quang Ngai by direct link`,async()=>{
 const f=await fixture(role)
 try {assert.equal(f.calls.length,0);assert.equal(f.doc.querySelector('h1'),null);assert.match(f.doc.body.textContent,/Chỉ Admin/)} finally {await f.close()}
})
