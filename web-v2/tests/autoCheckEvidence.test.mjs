import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { MessageChannel } from 'node:worker_threads'
import { readFileSync } from 'node:fs'

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import{createRoot}from'react-dom/client';import Page from './src/pages/AutoCheckPage';window.act=act;window.mount=user=>{window.root=createRoot(document.getElementById('root'));window.render(user)};window.render=user=>window.root.render(<Page user={user}/>);`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' },
  plugins: [{ name: 'api', setup(b) {
    b.onResolve({ filter: /\/lib\/(api|supabase)$/ }, args => ({ path: args.path.endsWith('/api') ? 'api' : 'auth', namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, args => ({ contents: args.path === 'api' ? 'export const veraApi=window.api;' : 'export function onVeraAuthStateChange(fn){window.authListeners.add(fn);return()=>window.authListeners.delete(fn)}', loader: 'js' }))
  } }],
})

const dashboard = { config: { status: 'RUNNING', threshold_minutes: 5 }, events: [], runs: [] }
const report = {
  source: 'facegate', cache_fresh: true, last_sync_at: '2026-10-10T22:00:00+07:00', start: '2026-10-09', end: '2026-10-10',
  evidence: { global_issue_count: 2, scoped_issue_count: 3, informational_issue_count: 4,
    reason_counts: { unmapped_reference: 2, unverified_status_type: 3, no_vera_shift: 4 },
    days: [{ date: '2026-10-10', archive_complete: true, archive_fresh: true, last_sync_at: '2026-10-10T22:00:00+07:00', global_issue_count: 2, scoped_issue_count: 3 }] },
}

test('status opens only explicitly and shows diagnostics in the modal without writes', async ctx => {
  const p = await page(ctx)
  const card = p.w.document.querySelector('[data-ui-key="u-e9f00f13cab7"]')
  assert.match(card.textContent, /Cấu hình Auto CheckĐã bật/)
  assert.equal(card.querySelector('.auto-check-ok'), null)
  assert.equal(p.dialog(), null)
  assert.equal(p.evidence(), null)
  assert.deepEqual(p.calls.map(call => call[0]), ['dashboard'])
  await p.click(p.button('Mở trạng thái'))
  assert.equal(p.dialog().getAttribute('aria-modal'), 'true')
  assert.match(p.dialog().textContent, /Trạng thái Auto Check/)
  assert.match(p.evidence().textContent, /Cần kiểm tra bằng chứng/)
  assert.match(p.evidence().textContent, /Chặn toàn cục: 2 · Chặn theo nhân viên\/ngày: 3 · Thông tin: 4/)
  assert.match(p.evidence().textContent, /09-10-2026 – 10-10-2026 \(giờ Việt Nam\), độc lập bộ lọc lịch sử/)
  assert.match(p.evidence().textContent, /10-10-2026 22:00:00/)
  assert.match(p.evidence().textContent, /Danh tính chưa xác nhận: 2/)
  assert.match(p.evidence().textContent, /Trạng thái lượt quét chưa xác minh: 3/)
  assert.ok(p.dialog().contains(p.evidence()))
  assert.equal(p.w.document.querySelector('.facegate-attendance-preview'), null)
  assert.deepEqual(p.calls.map(call => call[0]), ['dashboard', 'evidence'])
})

test('Tạm ẩn preserves report and expansion, Mở lại restores them, Close resets the view', async ctx => {
  const p = await page(ctx)
  const launcher = p.button('Mở trạng thái')
  await p.click(launcher)
  await p.click(p.evidence().querySelector('summary'))
  assert.equal(p.evidence().querySelector('details').open, true)
  await p.click(p.button('Tạm ẩn'))
  assert.equal(p.dialog(), null)
  assert.equal(p.evidence(), null)
  assert.equal(p.w.document.activeElement, launcher)
  assert.equal(p.w.document.body.style.overflow, '')
  await p.click(p.button('Mở lại trạng thái'))
  assert.equal(p.evidence().querySelector('details').open, true)
  assert.equal(p.calls.filter(call => call[0] === 'evidence').length, 1)
  await p.click(p.button('Close'))
  assert.equal(p.dialog(), null)
  assert.equal(p.w.document.activeElement, launcher)
  await p.click(p.button('Mở trạng thái'))
  assert.equal(p.evidence().querySelector('details').open, false)
  assert.equal(p.calls.filter(call => call[0] === 'evidence').length, 2)
  assert.ok(!p.calls.some(call => ['run', 'update'].includes(call[0])))
})

test('modal uses shared focus trap, Escape restoration and bounded mobile scrolling', async ctx => {
  const p = await page(ctx)
  const launcher = p.button('Mở trạng thái')
  await p.click(launcher)
  assert.equal(p.w.document.activeElement, p.dialog())
  assert.equal(p.w.document.body.style.overflow, 'hidden')
  const key = async (target, name, shiftKey = false) => p.w.act(async () => target.dispatchEvent(new p.w.KeyboardEvent('keydown', { key: name, shiftKey, bubbles: true, cancelable: true })))
  await key(p.dialog(), 'Tab')
  assert.equal(p.w.document.activeElement, p.button('Tạm ẩn'))
  await key(p.button('Tạm ẩn'), 'Tab', true)
  assert.equal(p.w.document.activeElement, p.evidence().querySelector('summary'))
  await key(p.evidence().querySelector('summary'), 'Tab')
  assert.equal(p.w.document.activeElement, p.button('Tạm ẩn'))
  await key(p.button('Tạm ẩn'), 'Escape')
  assert.equal(p.dialog(), null)
  assert.equal(p.w.document.activeElement, launcher)
  assert.equal(p.w.document.body.style.overflow, '')
  assert.match(readFileSync('src/components/EmployeeProfileModal.css', 'utf8'), /max-height: 100dvh/)
  assert.match(readFileSync('src/pages/AutoCheckPage.jsx', 'utf8'), /auto-check-status-body\{[^}]*overflow-y:auto/)
  assert.match(readFileSync('src/pages/AutoCheckPage.jsx', 'utf8'), /@media\(max-width:640px\)/)
})

for (const role of ['nhanvien', 'leader', 'quanly', 'letan']) {
  test(`${role} retains action grants and cannot launch or request Admin diagnostics`, async ctx => {
    const p = await page(ctx, { role, permissions: { auto_penalty: true, auto_penalty_run: true } })
    assert.equal(p.evidence(), null)
    assert.equal(p.button('Mở trạng thái'), undefined)
    assert.equal(p.button('Tạm dừng'), undefined)
    assert.ok(p.button('Chạy Auto Check'))
    assert.deepEqual(p.calls.map(call => call[0]), ['dashboard'])
  })
}

test('setting changes never open status or trigger diagnostic reads', async ctx => {
  const p = await page(ctx)
  await p.click(p.button('Tạm dừng'))
  assert.deepEqual(JSON.parse(JSON.stringify(p.calls.find(call => call[0] === 'update'))), ['update', { status: 'PAUSED' }])
  assert.equal(p.dialog(), null)
  assert.ok(!p.calls.some(call => call[0] === 'evidence' || call[0] === 'run'))
})

test('diagnostic failure clears prior healthy display and keeps explicit retry usable', async ctx => {
  let reads = 0
  const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: async () => {
    if (++reads === 1) return cleanReport
    throw Error('PRIVATE server detail must not be rendered')
  } })
  await p.click(p.button('Mở trạng thái'))
  assert.match(p.evidence().textContent, /Chưa thấy lỗi nguồn/)
  await p.click(p.button('Làm mới trạng thái'))
  assert.match(p.evidence().textContent, /Chưa đọc được tình trạng/)
  assert.doesNotMatch(p.evidence().textContent, /Chưa thấy lỗi nguồn|PRIVATE/)
  assert.equal(p.button('Làm mới trạng thái').disabled, false)
  assert.equal(p.button('Close').disabled, false)
})

for (const action of ['Tạm ẩn', 'Close']) {
  test(`late response after ${action} cannot reopen status`, async ctx => {
    const pending = deferred()
    let signal, reads = 0
    const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: options => {
      signal = options.signal; reads += 1
      return reads === 1 ? pending.promise : Promise.resolve(cleanReport)
    } })
    await p.click(p.button('Mở trạng thái'))
    assert.match(p.evidence().textContent, /Đang kiểm tra/)
    await p.click(p.button(action))
    assert.equal(signal.aborted, action === 'Close')
    await p.w.act(async () => pending.resolve(report))
    assert.equal(p.dialog(), null)
    assert.equal(p.evidence(), null)
    await p.click(p.button(action === 'Close' ? 'Mở trạng thái' : 'Mở lại trạng thái'))
    assert.equal(reads, action === 'Close' ? 2 : 1)
    assert.match(p.evidence().textContent, action === 'Close' ? /Chưa thấy lỗi nguồn/ : /Cần kiểm tra bằng chứng/)
  })
}

test('repeated opening and refresh clicks share one in-flight read', async ctx => {
  const pending = deferred()
  let reads = 0
  const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: () => { reads += 1; return pending.promise } })
  const launcher = p.button('Mở trạng thái')
  await p.w.act(async () => { launcher.click(); launcher.click(); launcher.click() })
  assert.equal(reads, 1)
  assert.equal(p.w.document.querySelectorAll('[role=dialog]').length, 1)
  assert.equal(p.button('Đang tải trạng thái…').getAttribute('aria-disabled'), 'true')
  await p.w.act(async () => pending.resolve(report))
})

test('pending refresh retains keyboard focus and traps Tab without duplicate reads', async ctx => {
  const pending = deferred()
  let reads = 0
  const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: () => {
    reads += 1
    return reads === 1 ? Promise.resolve(report) : pending.promise
  } })
  await p.click(p.button('Mở trạng thái'))
  const refresh = p.button('Làm mới trạng thái')
  await p.click(refresh)
  assert.equal(refresh.getAttribute('aria-disabled'), 'true')
  assert.equal(refresh.disabled, false)
  assert.equal(p.w.document.activeElement, refresh)
  const key = async (target, shiftKey = false) => p.w.act(async () => target.dispatchEvent(new p.w.KeyboardEvent('keydown', { key: 'Tab', shiftKey, bubbles: true, cancelable: true })))
  await key(refresh)
  assert.equal(p.w.document.activeElement, p.button('Tạm ẩn'))
  await key(p.button('Tạm ẩn'), true)
  assert.equal(p.w.document.activeElement, refresh)
  await p.click(refresh)
  assert.equal(reads, 2)
  await p.w.act(async () => pending.resolve(report))
  assert.equal(refresh.getAttribute('aria-disabled'), 'false')
})

test('same-role account change clears hidden cache and rejects old responses', async ctx => {
  const old = deferred(), latest = deferred(), signals = []
  let reads = 0
  const p = await page(ctx, { id: 'admin-a', employee_username: 'first', role: 'admin' }, { autoCheckEvidence: options => {
    signals.push(options.signal)
    return reads++ === 0 ? old.promise : latest.promise
  } })
  await p.click(p.button('Mở trạng thái'))
  await p.click(p.button('Tạm ẩn'))
  await p.render({ id: 'admin-b', employee_username: 'second', role: 'admin' })
  assert.equal(signals[0].aborted, true)
  assert.equal(p.button('Mở lại trạng thái'), undefined)
  assert.equal(p.dialog(), null)
  await p.click(p.button('Mở trạng thái'))
  await p.w.act(async () => latest.resolve(cleanReport))
  await p.w.act(async () => old.resolve(report))
  assert.match(p.evidence().textContent, /Chưa thấy lỗi nguồn/)
  assert.doesNotMatch(p.evidence().textContent, /Chặn toàn cục: 2/)
})

test('role removal immediately dismisses loaded status and removes the launcher', async ctx => {
  const p = await page(ctx)
  await p.click(p.button('Mở trạng thái'))
  await p.render({ id: 'admin-a', role: 'quanly', permissions: { auto_penalty: true } })
  assert.equal(p.dialog(), null)
  assert.equal(p.evidence(), null)
  assert.equal(p.button('Mở trạng thái'), undefined)
  assert.equal(p.w.document.body.style.overflow, '')
})

test('replacement auth session invalidates status even for the same Admin identity', async ctx => {
  const pending = deferred()
  let signal
  const p = await page(ctx, { id: 'admin-a', role: 'admin' }, { autoCheckEvidence: options => { signal = options.signal; return pending.promise } })
  await p.click(p.button('Mở trạng thái'))
  await p.w.act(async () => p.w.authListeners.forEach(fn => fn('TOKEN_REFRESHED', { user: { id: 'admin-a' } })))
  assert.equal(signal.aborted, true)
  await p.w.act(async () => pending.resolve(report))
  assert.equal(p.dialog(), null)
  assert.equal(p.evidence(), null)
  assert.ok(p.button('Mở trạng thái'))
})

test('unmount aborts diagnostics, restores overflow and tolerates a late response', async ctx => {
  const pending = deferred()
  let signal
  const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: options => { signal = options.signal; return pending.promise } })
  await p.click(p.button('Mở trạng thái'))
  await p.unmount()
  assert.equal(signal.aborted, true)
  await p.w.act(async () => pending.resolve(report))
  assert.equal(p.w.document.getElementById('root').textContent, '')
  assert.equal(p.w.document.body.style.overflow, '')
  assert.equal(p.w.authListeners.size, 0)
})

test('stale cache and incomplete archives warn without identity conflicts', async ctx => {
  const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: async () => ({ ...cleanReport, cache_fresh: false,
    evidence: { ...cleanReport.evidence, days: [{ ...cleanReport.evidence.days[0], archive_complete: false, archive_fresh: false }] } }) })
  await p.click(p.button('Mở trạng thái'))
  assert.match(p.evidence().textContent, /Cần kiểm tra bằng chứng/)
  assert.match(p.evidence().textContent, /Cache nguồn: Cũ hoặc chưa có/)
  assert.match(p.evidence().textContent, /Thiếu bản lưu; cũ hoặc chưa có/)
})

test('legacy source does not claim FaceGate diagnostic coverage', async ctx => {
  const p = await page(ctx, { role: 'admin' }, { autoCheckEvidence: async () => ({ ...report, source: 'timesoft', evidence: null }) })
  await p.click(p.button('Mở trạng thái'))
  assert.match(p.evidence().textContent, /Nguồn TimeSoft/)
  assert.match(p.evidence().textContent, /Chẩn đoán phạm vi bằng chứng chỉ áp dụng cho nguồn FaceGate/)
  assert.doesNotMatch(p.evidence().textContent, /Chặn toàn cục/)
})
const cleanReport = { ...report, evidence: { ...report.evidence, global_issue_count: 0, scoped_issue_count: 0,
  days: report.evidence.days.map(day => ({ ...day, global_issue_count: 0, scoped_issue_count: 0 })) } }
const deferred = () => { let resolve, reject; const promise = new Promise((a, b) => { resolve = a; reject = b }); return { promise, resolve, reject } }

async function page(ctx, user = { id: 'admin-a', role: 'admin' }, overrides = {}) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://test.invalid', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window, channels = [], calls = []
  w.MessageChannel = class extends MessageChannel { constructor() { super(); channels.push(this) } }
  w.IS_REACT_ACT_ENVIRONMENT = true
  w.authListeners = new Set()
  // jsdom has no layout; expose mounted controls to the shared focus trap.
  w.HTMLElement.prototype.getClientRects = function () { return this.isConnected ? [{}] : [] }
  w.api = {
    autoCheck: async (...args) => { calls.push(['dashboard', ...args]); return dashboard },
    autoCheckEvidence: async (...args) => { calls.push(['evidence', ...args]); return report },
    updateAutoCheck: async body => { calls.push(['update', body]); return {} },
    runAutoCheck: async () => { calls.push(['run']); return {} },
    ...overrides,
  }
  w.eval(built.outputFiles[0].text)
  await w.act(async () => w.mount(user))
  let mounted = true
  const unmount = async () => { if (mounted) { await w.act(async () => w.root.unmount()); mounted = false } }
  ctx.after(async () => { await unmount(); channels.forEach(c => { c.port1.close(); c.port2.close() }); w.close() })
  return { w, calls, unmount, text: () => w.document.body.textContent,
    render: async user => w.act(async () => w.render(user)),
    dialog: () => w.document.querySelector('[role=dialog]'),
    evidence: () => w.document.querySelector('.auto-check-evidence'),
    button: text => [...w.document.querySelectorAll('button')].find(button => button.textContent.trim() === text),
    click: async node => w.act(async () => { node.focus(); node.click(); await new Promise(resolve => w.setTimeout(resolve, 0)) }),
  }
}
