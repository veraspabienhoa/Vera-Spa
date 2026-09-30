import test from 'node:test'
import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Page from './src/pages/AttendancePage';const root=createRoot(document.getElementById('root'));window.act=act;window.mount=(permissions,initialTab)=>act(async()=>root.render(<Page user={{permissions}} initialTab={initialTab}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic',
  plugins: [{ name: 'pages', setup(b) {
    b.onResolve({ filter: /^\.\/(SnapshotPage|CheckinHistoryPage)$/ }, args => ({ path: args.path, namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: `import React,{useEffect} from 'react';export default function Page(){useEffect(()=>{window.loaded.push('${args.path}')},[]);return <div data-page="${args.path}">Loaded</div>}`, loader: 'jsx', resolveDir: process.cwd() }))
  } }],
})
async function mount(permissions, initialTab = 'snapshot') {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.IS_REACT_ACT_ENVIRONMENT = true; w.loaded = []
  w.eval(built.outputFiles[0].text); await w.mount(permissions, initialTab)
  return dom
}
test('attendance tabs mount only selected content and support keyboard navigation', async () => {
  const dom = await mount({ snapshot_today: true, device_history_view: true }), w = dom.window
  try {
    assert.equal(w.document.querySelector('h1').textContent, 'CHẤM CÔNG')
    assert.equal(w.loaded.join(','), './SnapshotPage')
    const tabs = [...w.document.querySelectorAll('[role="tab"]')]
    assert.equal(tabs.length, 2)
    await w.act(async () => tabs[1].click())
    assert.equal(w.document.querySelector('[data-page]').dataset.page, './CheckinHistoryPage')
    assert.equal(tabs[1].getAttribute('aria-selected'), 'true')
    await w.act(async () => tabs[1].dispatchEvent(new w.KeyboardEvent('keydown', { key: 'Home', bubbles: true, cancelable: true })))
    assert.equal(w.document.activeElement, tabs[0])
    assert.equal(w.document.querySelector('[data-page]').dataset.page, './SnapshotPage')
  } finally { await w.unmount(); w.close() }
})
for (const [permissions, initial, expected] of [
  [{ device_history_view: true }, 'snapshot', './CheckinHistoryPage'],
  [{ snapshot_today: true }, 'history', './SnapshotPage'],
  [{ snapshot_today: true, device_history_view: true }, 'history', './CheckinHistoryPage'],
  [{}, 'history', ''],
]) test(`permissions and legacy initial history: ${JSON.stringify(permissions)}`, async () => {
  const dom = await mount(permissions, initial), w = dom.window
  try { assert.equal(w.loaded.join(','), expected) }
  finally { await w.unmount(); w.close() }
})
test('sidebar consolidates history into attendance and old route remains supported', () => {
  const shell = readFileSync('src/components/AppShell.jsx', 'utf8')
  assert.ok(!shell.includes("id: 'checkin-history'"))
  assert.ok(shell.includes("anyPermission: ['snapshot_today', 'device_history_view']"))
  const app = readFileSync('src/App.jsx', 'utf8')
  assert.ok(app.includes('initialTab="history"'))
  assert.ok(!readFileSync('src/pages/SnapshotPage.jsx', 'utf8').includes('TimeSoft'))
})
