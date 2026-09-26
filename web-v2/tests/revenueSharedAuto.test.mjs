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

async function fixture(role, initial = 'auto', legacy = false) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { pretendToBeVisual: true })
  let source = initial, revision = 1
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
        return response({ source, revision })
      }
      if (path.endsWith('/summary')) return response({ source, source_revision: legacy ? undefined : revision,
        total_income: 1760, total_expense: 190.25, net_income: 1569.75, period_tip: 20, balance: 1549.75,
        start_date: '2026-09-05', start_date_label: '05-09-2026', current_date: '2026-09-26', current_date_label: '26-09-2026',
        period_tip_start: '2026-09-16', period_tip_end: '2026-09-26',
        can_edit_tip: true, can_create_entry: source !== 'auto', can_edit_entry: source !== 'auto', can_delete_entry: source !== 'auto',
      })
      if (path.endsWith('/purchase-reconcile')) return response({ source: legacy ? undefined : source, source_revision: legacy ? undefined : revision,
        start_date: '2026-09-05', end_date: '2026-09-26', purchase_rows: [],
        ledger_rows: [{ id: 'auto:2026-09-05:Thu', date:'2026-09-05', date_label:'05-09-2026', type:'Thu', amount:1760, note:'Doanh thu dịch vụ + TIP', read_only: source === 'auto' }],
      })
      if (path.endsWith('/live-tour/reports')) return response({reports:[{business_date:'2026-09-20',tip:20}]})
      if (path.endsWith('/tip-summary')) return response({ source, period_tip: 20 })
      if (path.endsWith('/tip-period')) return response({ period_tip:20, balance:1549.75, period_tip_start:'2026-09-16', period_tip_end:'2026-09-26' })
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
  return { doc:dom.window.document, calls,
    button(text) { return [...dom.window.document.querySelectorAll('button')].find(b=>b.textContent.includes(text)) },
    async externalMode(mode) { source=mode; revision+=1; await act(async()=>dom.window.dispatchEvent(new dom.window.Event('focus'))); await act(async()=>{await new Promise(resolve=>setTimeout(resolve,300))}) },
    async close() { await act(async()=>root.unmount()); dom.window.close(); for(const [key,desc] of Object.entries(descriptors)){ if(desc) Object.defineProperty(globalThis,key,desc); else delete globalThis[key] } },
  }
}

for (const role of ['admin','giamdoc','quanly','letan','nhanvien']) {
  test(`${role}: Auto is shared and all Manual write controls are absent`, async () => {
    const f = await fixture(role)
    try {
      assert.match(f.doc.body.textContent,/Auto · Tự động hệ thống/)
      assert.equal(f.doc.querySelector('.revenue-entry-form'),null)
      assert.equal(f.button('Import thêm mới'),undefined)
      assert.equal(f.button('Sửa dòng đã chọn'),undefined)
      assert.equal(f.button('Xóa dòng đã chọn'),undefined)
      assert.match(f.doc.querySelector('.ledger-table').textContent,/05-09-2026/)
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
    assert.match(f.doc.querySelector('.ledger-table').textContent,/05-09-2026/)
    assert.match(f.doc.body.textContent,/Cần chạy Deploy VPS Production/)
    assert.equal(f.button('Auto · Tự động hệ thống').disabled,true)
    assert.equal(f.button('Lưu Tiền TIP').disabled,false)
  } finally { await f.close() }
})
