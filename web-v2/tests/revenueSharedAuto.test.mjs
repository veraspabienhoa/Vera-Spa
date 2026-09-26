import assert from 'node:assert/strict'
import test from 'node:test'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const require = createRequire(import.meta.url)
const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/RevenuePage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react/jsx-runtime', 'react-dom', 'lucide-react'], loader: { '.css': 'empty' },
  define: { 'import.meta.env.VITE_VERA_API_BASE_URL': '"https://api.invalid"' },
  plugins: [{ name: 'revenue-fixture', setup(b) {
    b.onResolve({ filter: /(?:\/supabase|\/UiCustomText|\/UiToolbar|\/usePageRefresh)$/ }, args => ({ path: args.path.split('/').at(-1), namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, args => ({ loader: 'js', contents:
      args.path === 'supabase' ? 'export const getCurrentSession=async()=>({access_token:"synthetic"});' :
      args.path === 'UiCustomText' ? 'export default function Text({children}){return children}' :
      args.path === 'usePageRefresh' ? 'export default function Hook(){}' :
      'import React from "react"; export default function Toolbar({children,...props}){return React.createElement("div",props,children)}',
    }))
  } }],
})

async function fixture(role, initial = 'auto', legacy = false, rowCount = 1, savedEnd = '2026-09-26', unified = false, savedStart = '2026-09-16', ledgerFixture = null) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
  let source = initial, revision = 1, hold = false, pending = null, today = '2026-09-26', dataRevision = 1
  const calls = []
  const names = ['window','document','navigator','ResizeObserver','requestAnimationFrame','cancelAnimationFrame','IS_REACT_ACT_ENVIRONMENT','fetch']
  const descriptors = Object.fromEntries(names.map(name => [name, Object.getOwnPropertyDescriptor(globalThis, name)]))
  const response = result => ({ ok: true, json: async () => result })
  const values = {
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
        const result={ok:true,report_version:1,report_basis:'shared_history_and_system',source,source_revision:revision,
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
          ledger_rows:ledgerFixture ? ledgerFixture.filter(row=>row.date>=start && row.date<=end) : Array.from({length:rowCount},(_,i)=>({id:`auto:${i}`,date:'2025-09-05',date_label:'05-09-2025',type:'Thu',amount:1760,note:`Doanh thu dịch vụ + TIP ${i+1}`,read_only:source==='auto'})),
        })
      }
      if (path.endsWith('/ledger/export.xlsx')) return {ok:true,blob:async()=>new Blob(['synthetic full export'])}
      if (path.endsWith('/live-tour/reports')) return response({reports:[{business_date:'2026-09-20',tip:20}]})
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

for (const role of ['admin','giamdoc','quanly','letan','nhanvien']) {
  test(`${role}: Auto is shared and Manual form stays hidden and the Auto toolbar cannot write`, async () => {
    const f = await fixture(role)
    try {
      assert.match(f.doc.body.textContent,/Auto · Tự động hệ thống/)
      assert.equal(f.doc.querySelector('.revenue-entry-form'),null)
      assert.equal(f.doc.querySelector('.revenue-report-date-form'),null)
      assert.equal(Boolean(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]')),['admin','giamdoc'].includes(role))
      if(role==='admin') assert.equal(f.button('Import thêm mới').disabled,true); else assert.equal(f.button('Import thêm mới'),undefined)
      if(role==='admin') assert.equal(f.button('Sửa dòng đã chọn').disabled,true); else assert.equal(f.button('Sửa dòng đã chọn'),undefined)
      if(role==='admin') assert.equal(f.button('Xóa dòng đã chọn').disabled,true); else assert.equal(f.button('Xóa dòng đã chọn'),undefined)
      assert.match(f.doc.querySelector('.ledger-table').textContent,/05-09-2025/)
      if(role!=='admin') assert.equal(f.doc.querySelector('.revenue-source-toggle'),null)
      assert.equal(f.calls.filter(c=>c.path.endsWith('/purchase-reconcile')).length,1)
      assert.equal(f.calls.some(c=>c.path.includes('live-tour/reports')),false)
    } finally { await f.close() }
  })
}

test('admin persists global mode and Auto keeps five Manual cards and date-only TIP save', async () => {
  const f=await fixture('admin','manual')
  try {
    assert.ok(f.doc.querySelector('.revenue-entry-form'))
    await act(async()=>f.button('Auto · Tự động hệ thống').click())
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))})
    assert.deepEqual(f.calls.find(c=>c.path.endsWith('/source')&&c.method==='PUT').body,{source:'auto',revision:1})
    assert.equal(f.doc.querySelector('.revenue-entry-form'),null)
    assert.equal(f.doc.querySelectorAll('.revenue-grid .revenue-card').length,5)
    assert.ok(f.doc.querySelector('[aria-label="Ngày bắt đầu Tiền TIP"]'))
    assert.equal(f.doc.querySelector('[aria-label="Tiền TIP trong kỳ tự động"]').readOnly,true)
    assert.equal(f.button('Lưu Tiền TIP').disabled,false)
    await act(async()=>f.button('Lưu Tiền TIP').click())
    assert.deepEqual(f.calls.find(c=>c.path.endsWith('/tip-period')).body,{start_date:'2026-09-16',end_date:'2026-09-26'})
  } finally { await f.close() }
})

test('an already open Manual page locks after another admin changes the shared mode', async()=>{
  const f=await fixture('letan','manual')
  try {
    assert.ok(f.doc.querySelector('.revenue-entry-form'))
    await f.externalMode('auto')
    assert.equal(f.doc.querySelector('.revenue-entry-form'),null)
    assert.equal(f.button('Sửa dòng đã chọn'),undefined)
    assert.equal(f.calls.some(c=>c.method!=='GET'),false)
  } finally { await f.close() }
})

 test('older VPS keeps Manual usable until backend deployment', async()=>{
  const f=await fixture('admin','manual',true)
  try {
    assert.ok(f.doc.querySelector('.revenue-entry-form'))
    assert.match(f.doc.querySelector('.ledger-table').textContent,/05-09-2025/)
    assert.match(f.doc.body.textContent,/Cần chạy Deploy VPS Production/)
    assert.equal(f.button('Auto · Tự động hệ thống').disabled,true)
    assert.equal(f.button('Lưu Tiền TIP').disabled,false)
  } finally { await f.close() }
})


test('Auto uses the displayed end date for every total and keeps it through refresh and saving', async()=>{
  const f=await fixture('admin')
  try {
    const summaries=()=>f.calls.filter(c=>c.path.endsWith('/summary'))
    const amount=kind=>f.doc.querySelector(`.revenue-card.${kind}`).textContent
    const n=summaries().length
    const date=f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]')
    assert.equal(f.doc.querySelector('.revenue-report-date-form'),null,'one end date, no separate report form')
    for (const invalid of ['24-09-20','31-09-2026','27-09-2026']) {
      await f.change(date,invalid)
      await act(async()=>f.button('Lưu Tiền TIP').click())
      assert.equal(summaries().length,n,'invalid/partial date does not query with an old value')
      assert.equal(f.calls.some(c=>c.method==='PUT'),false,'invalid/partial date cannot save the previous date')
    }
    await f.change(date,'24-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))})
    assert.equal(summaries().length,n+1,'one summary request per complete date')
    assert.deepEqual(Object.fromEntries(new URL(summaries().at(-1).url).searchParams),{source:'auto',time_range:'custom',start:'2025-09-05',end:'2026-09-24'})
    assert.equal(new URL(f.calls.filter(c=>c.path.endsWith('/tip-summary')).at(-1).url).searchParams.get('end'),'2026-09-24')
    assert.equal(f.doc.querySelector('.revenue-report-cutoff strong').textContent,'24-09-2026')
    assert.match(amount('income'),/1\.000đ/);assert.match(amount('expense'),/100đ/);assert.match(amount('net'),/900đ/);assert.match(amount('balance'),/880đ/)
    await f.change(f.doc.querySelector('[aria-label="Ngày bắt đầu Tiền TIP"]'),'17-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))})
    assert.equal(summaries().length,n+1,'TIP start must not move the revenue start away from 05-09-2025')
    await act(async()=>f.button('Lưu Tiền TIP').click())
    assert.match(amount('balance'),/880đ/,'save response cannot replace the selected report balance')
    assert.deepEqual(f.calls.find(c=>c.path.endsWith('/tip-period')).body,{start_date:'2026-09-17',end_date:'2026-09-24'})
    await f.externalMode('auto')
    assert.equal(new URL(summaries().at(-1).url).searchParams.get('end'),'2026-09-24')
    assert.match(amount('income'),/1\.000đ/)
    const refreshed=summaries().length
    await f.change(date,'')
    assert.equal(summaries().length,refreshed,'clearing date does not reset to all time')
    assert.match(amount('income'),/1\.000đ/)
    await act(async()=>f.button('Dùng ngày này').click())
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))})
    assert.equal(new URL(summaries().at(-1).url).searchParams.get('end'),'2026-09-26')
    assert.equal(f.doc.querySelector('.revenue-report-cutoff strong').textContent,'26-09-2026')
    assert.equal(date.value,'26-09-2026')
    assert.match(amount('income'),/1\.760đ/)
    assert.equal(f.calls.filter(c=>c.method!=='GET').length,1,'only explicit TIP saving writes')
  } finally {await f.close()}
})

test('Auto opens the saved TIP end date as its report end date',async()=>{
  const f=await fixture('admin','auto',false,1,'2026-09-24')
  try {
    assert.equal(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]').value,'24-09-2026')
    assert.equal(f.doc.querySelector('.revenue-report-cutoff strong').textContent,'24-09-2026')
    assert.match(f.doc.querySelector('.revenue-card.income').textContent,/1\.000đ/)
    assert.equal(new URL(f.calls.filter(c=>c.path.endsWith('/summary')).at(-1).url).searchParams.get('end'),'2026-09-24')
    assert.equal(f.calls.some(c=>c.method!=='GET'),false)
  } finally {await f.close()}
})

test('Manual TIP end date retains its existing independent behavior',async()=>{
  const f=await fixture('admin','manual')
  try {
    const before=f.calls.filter(c=>c.path.endsWith('/summary')).length
    await f.change(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]'),'24-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))})
    assert.equal(f.calls.filter(c=>c.path.endsWith('/summary')).length,before)
    assert.match(f.doc.querySelector('.revenue-card.income').textContent,/1\.760đ/)
  } finally {await f.close()}
})


for(const initial of ['manual','auto']) test(`${initial}: one shared response keeps all totals and TIP on the selected period`,async()=>{
  const f=await fixture('admin',initial,false,1,'2026-09-26',true)
  try{
    const reports=()=>f.calls.filter(c=>c.path.endsWith('/period-report'))
    const money=kind=>f.doc.querySelector(`.revenue-card.${kind}`).textContent
    assert.equal(reports().length,1,'opening initializes fields without refetching the same report')
    assert.equal(f.calls.some(c=>/\/(summary|tip-summary)$/.test(c.path)),false,'no independent total/TIP requests')
    await f.change(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]'),'24-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,260))})
    assert.equal(reports().length,2)
    assert.deepEqual(Object.fromEntries(new URL(reports().at(-1).url).searchParams),{start:'2026-09-16',end:'2026-09-24'})
    assert.equal(f.doc.querySelector('[aria-label="Tiền TIP trong kỳ tự động"]').value,'20đ')
    assert.match(money('tip'),/20đ/);assert.match(money('income'),/1\.000đ/);assert.match(money('balance'),/880đ/)
    const detail=f.calls.filter(c=>c.path.endsWith('/purchase-reconcile')).at(-1)
    assert.equal(new URL(detail.url).searchParams.get('report_end'),'2026-09-24')
    assert.equal(new URL(detail.url).searchParams.get('canonical'),'true')
    await act(async()=>f.button('Lưu Tiền TIP').click())
    assert.deepEqual(f.calls.find(c=>c.path.endsWith('/report-period')).body,{start_date:'2026-09-16',end_date:'2026-09-24'})
    await f.externalMode(initial==='auto'?'manual':'auto')
    assert.equal(new URL(reports().at(-1).url).searchParams.get('end'),'2026-09-24')
    assert.match(money('income'),/1\.000đ/);assert.match(money('expense'),/100đ/);assert.match(money('tip'),/20đ/);assert.match(money('balance'),/880đ/)
    assert.equal(f.doc.querySelector('[aria-label="Tiền TIP trong kỳ tự động"]').value,'20đ')
    if(initial==='auto'){
      await act(async()=>f.button('Sổ nhập tay').click())
      assert.equal(new URL(f.calls.filter(c=>c.path.endsWith('/purchase-reconcile')).at(-1).url).searchParams.has('canonical'),false)
      assert.match(money('income'),/1\.000đ/,'raw ledger inspection does not change the common report')
    }
  }finally{await f.close()}
})

test('late report cannot overwrite a newer selected date or mix the TIP field and card',async()=>{
  const f=await fixture('admin','auto',false,1,'2026-09-24',true)
  try{
    f.holdNextReport()
    await f.change(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]'),'26-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,230))})
    // Simulate the next selection arriving while the transport ignores abort.
    await f.change(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]'),'24-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,230))})
    await act(async()=>f.releaseReport())
    assert.equal(f.doc.querySelector('.revenue-report-cutoff strong').textContent,'24-09-2026')
    assert.equal(f.doc.querySelector('.revenue-grid').getAttribute('aria-busy'),'false')
    assert.equal(f.doc.querySelector('[aria-label="Tiền TIP trong kỳ tự động"]').value,'20đ')
    assert.match(f.doc.querySelector('.revenue-card.tip').textContent,/20đ/)
    assert.match(f.doc.querySelector('.revenue-card.income').textContent,/1\.000đ/)
  }finally{await f.close()}
})


test('independent Auto accepts start-first single-day editing and hides old TIP for invalid drafts', async()=>{
  const f=await fixture('admin','auto',false,1,'2026-09-24',2,'2025-09-16')
  try {
    const start=f.doc.querySelector('[aria-label="Ngày bắt đầu Tiền TIP"]'), end=f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]')
    const tip=()=>f.doc.querySelector('[aria-label="Tiền TIP trong kỳ tự động"]').value
    const requests=()=>f.calls.filter(c=>c.path.endsWith('/period-report'))
    await f.change(start,'25-09-2026')
    assert.equal(tip(),'—','do not show old period money beside a reversed period')
    await f.change(end,'25-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,280))})
    assert.deepEqual(Object.fromEntries(new URL(requests().at(-1).url).searchParams),{start:'2026-09-25',end:'2026-09-25'})
    assert.equal(tip(),'15.450.000đ')
    assert.equal(f.doc.querySelector('[aria-label="Ngày bắt đầu Tiền TIP"]').getAttribute('aria-invalid'),null)
    await act(async()=>f.button('Lưu Tiền TIP').click())
    assert.deepEqual(f.calls.filter(c=>c.method==='PUT').at(-1).body,{start_date:'2026-09-25',end_date:'2026-09-25'})
    const count=requests().length
    await f.change(start,'25-09-20')
    assert.equal(tip(),'—')
    assert.equal(f.button('Lưu Tiền TIP').disabled,true)
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,280))})
    assert.equal(requests().length,count,'incomplete text cannot reuse a previous date')
  } finally { await f.close() }
})

test('independent purchase report total includes all filtered rows and ignores the TIP cutoff',async()=>{
  const f=await fixture('admin','auto',false,105,'2026-09-24',2)
  try {
    await act(async()=>f.button('Báo cáo mua hàng').click())
    const call=f.calls.filter(c=>c.path.endsWith('/purchases')).at(-1)
    assert.ok(call)
    assert.equal(new URL(call.url).searchParams.has('report_end'),false)
    const total=()=>f.doc.querySelector('[aria-label="Tổng mua theo bộ lọc"]').textContent
    assert.match(total(),/1\.050đ/); assert.match(total(),/105 dòng/)
    assert.equal(f.doc.querySelectorAll('.report-table tbody tr').length,100)
    await f.change(f.doc.querySelector('[placeholder="Tìm hàng hóa"]'),'Hàng 1')
    assert.match(total(),/170đ/); assert.match(total(),/17 dòng/)
    await f.change(f.doc.querySelector('[placeholder="Tìm người đặt"]'),'khong-co')
    assert.match(total(),/0đ/); assert.match(total(),/0 dòng/)
  } finally { await f.close() }
})

test('Manual ledger and export can inspect September 24 while the summary stays at September 21',async()=>{
  const rows=[['Thu',49250000],['Chi',54000000],['Chi',202000]].map(([type,amount],i)=>({
    id:i+1,date:'2026-09-24',date_label:'24-09-2026',type,amount,note:`Synthetic entry ${i+1}`}))
  const f=await fixture('admin','manual',false,3,'2026-09-21',2,'2026-09-16',rows)
  try {
    const details=()=>f.calls.filter(c=>c.path.endsWith('/purchase-reconcile'))
    assert.equal(new URL(details().at(-1).url).searchParams.has('report_end'),false)
    assert.equal(f.doc.querySelectorAll('.ledger-table tbody tr').length,3)
    assert.equal(f.doc.querySelector('.revenue-report-cutoff strong').textContent,'21-09-2026')
    const field=label=>[...f.doc.querySelectorAll('.detail-filter-panel label')].find(node=>node.firstChild?.textContent===label)?.querySelector('input[type="text"]')
    await f.change(field('Ngày'),'24-09-2026')
    assert.equal(f.doc.querySelectorAll('.ledger-table tbody tr').length,3)
    assert.match(f.doc.querySelector('.ledger-summary-head').textContent,/49\.250\.000đ/)
    assert.match(f.doc.querySelector('.ledger-summary-head').textContent,/54\.202\.000đ/)
    f.doc.addEventListener('click', event=>{if(event.target.closest('a[download]'))event.preventDefault()})
    await act(async()=>f.button('Xuất Excel').click())
    let query=new URL(f.calls.find(c=>c.path.endsWith('/ledger/export.xlsx')).url).searchParams
    assert.equal(query.has('report_end'),false)
    assert.equal(query.get('transaction_date'),'2026-09-24')
    await f.change(field('Đến ngày'),'24-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20))})
    query=new URL(details().at(-1).url).searchParams
    assert.equal(query.get('start'),'2026-09-24','editing one date retains the other displayed bound')
    assert.equal(query.get('end'),'2026-09-24')
    await f.change(field('Từ ngày'),'24-09-2026')
    await act(async()=>{await new Promise(resolve=>setTimeout(resolve,20))})
    assert.equal(new URL(details().at(-1).url).searchParams.get('start'),'2026-09-24')
    assert.equal(f.doc.querySelectorAll('.ledger-table tbody tr').length,3)
    assert.equal(f.doc.querySelector('.revenue-report-cutoff strong').textContent,'21-09-2026')
    assert.equal(f.calls.some(c=>c.method!=='GET'),false,'inspecting the ledger must not change the saved report or money')
  } finally { await f.close() }
})

for(const source of ['manual','auto','manual_tip_auto']) test(`${source}: all ledger dates stay live beyond the TIP cutoff and preserve explicit filters`,async()=>{
  const row=(id,date,amount)=>({id,date,date_label:date.split('-').reverse().join('-'),type:'Thu',amount,note:`Synthetic ${id}`,read_only:source==='auto'})
  const rows=[row(1,'2024-01-02',100),row(2,'2026-09-24',200),row(3,'2026-09-26',300)]
  const f=await fixture('admin',source,false,3,'2026-09-21',2,'2026-09-16',rows)
  try {
    const details=()=>f.calls.filter(c=>c.path.endsWith('/purchase-reconcile'))
    const query=()=>new URL(details().at(-1).url).searchParams
    const field=label=>[...f.doc.querySelectorAll('.detail-filter-panel label')].find(node=>node.firstChild?.textContent===label)?.querySelector('input[type="text"]')
    if(source==='manual_tip_auto'){
      await f.change(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]'),'21-09-2026')
      await act(async()=>{await new Promise(resolve=>setTimeout(resolve,320))})
    }
    assert.equal(query().get('live_ledger'),'true')
    assert.equal(query().has('report_end'),false)
    assert.equal(f.doc.querySelectorAll('.ledger-table tbody tr').length,3)
    assert.match(f.doc.querySelector('.ledger-table').textContent,/02-01-2024/)
    assert.equal(field('Đến ngày').value,'26-09-2026')
    await f.updateLedger([...rows,row(4,'2026-09-27',400)],'2026-09-27')
    assert.equal(f.doc.querySelectorAll('.ledger-table tbody tr').length,4)
    assert.equal(field('Đến ngày').value,'27-09-2026')
    assert.match(f.doc.querySelector('.ledger-summary-head').textContent,/1\.000đ/)
    assert.equal(f.doc.querySelector('[aria-label="Đến ngày Tiền TIP"]').value,'21-09-2026','refresh must preserve the deliberate TIP period')
    await f.change(field('Ngày'),'24-09-2026')
    await f.updateLedger([row(2,'2026-09-24',250),row(4,'2026-09-27',400)])
    assert.equal(f.doc.querySelectorAll('.ledger-table tbody tr').length,1)
    assert.match(f.doc.querySelector('.ledger-summary-head').textContent,/250đ/)
    assert.equal(field('Ngày').value,'24-09-2026')
    f.doc.addEventListener('click',event=>{if(event.target.closest('a[download]'))event.preventDefault()})
    await act(async()=>f.button('Xuất Excel').click())
    const exported=new URL(f.calls.filter(c=>c.path.endsWith('/ledger/export.xlsx')).at(-1).url).searchParams
    assert.equal(exported.get('live_ledger'),'true')
    assert.equal(exported.get('transaction_date'),'2026-09-24')
    assert.equal(exported.has('report_end'),false)
    assert.equal(f.calls.some(c=>c.method!=='GET'),false)
  } finally { await f.close() }
})
