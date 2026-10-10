import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'
import { canSharePdf, canSharePng, shareCustomerCountPdf, shareCustomerCountPng } from '../src/lib/customerCountShare.js'

for (const [format, mime, canShare, share] of [['PDF', 'application/pdf', canSharePdf, shareCustomerCountPdf], ['PNG', 'image/png', canSharePng, shareCustomerCountPng]]) {
  test(`${format} native share synchronously passes only the prepared file`, async () => {
    const file = { name: `VERA_SoLuongKhach.${format.toLowerCase()}`, type: mime }, calls = []
    const browser = { canShare: data => data.files[0] === file, share: data => { calls.push(data); return Promise.resolve() } }
    assert.equal(canShare(file, browser), true)
    const result = share(file, browser)
    assert.equal(calls.length, 1, 'share starts in the original click before any await')
    assert.equal(calls[0].files[0], file); assert.equal(calls[0].url, undefined)
    await result
    assert.throws(() => share(file, { canShare: () => false, share: () => { throw Error('must not call') } }), new RegExp(`tải ${format}`))
    assert.equal(canShare(file, { share() {}, canShare: () => { throw Error('blocked') } }), false)
    assert.equal(canShare(null, browser), false); assert.equal(canShare(file, undefined), false)
  })
}
const built = await build({
  stdin: { contents: "export { default } from './src/components/CustomerCountShareDialog'", loader: 'jsx', resolveDir: process.cwd() },
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic', external: ['react', 'react-dom', 'react/jsx-runtime'], loader: { '.css': 'empty' },
  plugins: [{ name: 'api', setup(b) {
    b.onResolve({ filter: /\/lib\/api$/ }, () => ({ path: 'api', namespace: 'fixture' }))
    b.onLoad({ filter: /.*/, namespace: 'fixture' }, () => ({ contents: "export const veraApi={readCustomerCountPdf:(...args)=>window.prepareReport('pdf',...args),readCustomerCountPng:(...args)=>window.prepareReport('png',...args)}" }))
  } }],
})
function deferred() { let resolve, reject; const promise = new Promise((done, fail) => { resolve = done; reject = fail }); return { promise, resolve, reject } }
const filters = { date_from: '2026-10-01', date_to: '2026-10-31', date: '', employee: 'Mạnh Đạt', customer: 'Khách', service: 'Body', bill_no: 'HD', total_amount: 0 }
async function fixture({ prepare, share, canShare = () => true } = {}) {
  const dom = new JSDOM('<body><button id="opener">Báo cáo</button><div id="root"></div></body>', { url: 'https://example.test' })
  const values = { window: dom.window, document: dom.window.document, navigator: dom.window.navigator, File: dom.window.File, URL: dom.window.URL, IS_REACT_ACT_ENVIRONMENT: true }
  const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { value, configurable: true })
  const requests = [], shares = [], revoked = [], urls = [], downloads = []
  let closes = 0, mounted = true
  const blobs = { pdf: new window.Blob(['%PDF-1.4'], { type: 'application/pdf' }), png: new window.Blob([new Uint8Array([137,80,78,71,13,10,26,10])], { type: 'image/png' }) }
  window.prepareReport = (format, actualFilters, options) => { requests.push({ format, filters: actualFilters, signal: options.signal }); return prepare ? prepare(format, actualFilters, options, blobs) : Promise.resolve(blobs[format]) }
  URL.createObjectURL = file => { const url = `blob:prepared-${urls.length + 1}`; urls.push({ url, file }); return url }
  URL.revokeObjectURL = value => revoked.push(value)
  dom.window.HTMLAnchorElement.prototype.click = function () { downloads.push({ href: this.href, name: this.download }) }
  navigator.canShare = canShare; navigator.share = data => { shares.push(data); return share ? share(data) : Promise.resolve() }
  const mod = { exports: {} }; new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
  const { createRoot } = await import('react-dom/client'), root = createRoot(document.querySelector('#root'))
  document.querySelector('#opener').focus()
  const render = async value => act(async () => root.render(React.createElement(mod.exports.default, { filters: value, onClose: () => { closes += 1 } })))
  const unmount = async () => { if (mounted) { await act(async () => root.unmount()); mounted = false } }
  await render(filters)
  return { dom, blobs, requests, shares, revoked, urls, downloads, render, unmount, closes: () => closes,
    button: text => [...document.querySelectorAll('button')].find(node => node.textContent === text),
    download: format => document.querySelector(`a[download="VERA_SoLuongKhach.${format}"]`),
    dispose: async () => { try { await unmount() } finally { dom.window.close(); for (const [key, descriptor] of Object.entries(saved)) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete globalThis[key] } } },
  }
}

test('dialog prepares complete PDF/PNG with identical filters and retains all PDF actions', async () => {
  const png = deferred(), f = await fixture({ prepare: (format, _filters, _options, blobs) => format === 'png' ? png.promise : Promise.resolve(blobs.pdf) })
  try {
    assert.deepEqual(f.requests.map(({ format, filters: scope }) => ({ format, filters: scope })), [{ format: 'pdf', filters }, { format: 'png', filters }])
    assert.match(document.body.textContent, /PDF đã sẵn sàng/); assert.match(document.body.textContent, /Đang tạo PNG/)
    assert.ok(f.download('pdf')); assert.ok(f.button('Chia sẻ qua Zalo')); assert.equal(document.querySelector('a[target="_blank"]').textContent, 'Xem PDF')
    assert.equal(f.download('png'), null)
    await act(async () => png.resolve(f.blobs.png))
    assert.equal(f.shares.length, 0, 'preparing never opens share automatically')
    assert.match(document.body.textContent, /PNG đã sẵn sàng/); assert.match(document.body.textContent, /Ảnh toàn bộ báo cáo/)
    assert.equal(f.urls[1].file.type, 'image/png'); assert.equal(f.urls[1].file.name, 'VERA_SoLuongKhach.png'); assert.ok(f.button('Chia sẻ PNG'))
    await act(async () => f.download('png').click())
    assert.deepEqual(f.downloads, [{ href: f.urls[1].url, name: 'VERA_SoLuongKhach.png' }]); assert.equal(f.requests.length, 2)
    await f.unmount()
    assert.ok(f.requests.every(request => request.signal.aborted)); assert.deepEqual(f.revoked, f.urls.map(item => item.url)); assert.equal(document.activeElement.id, 'opener')
  } finally { await f.dispose() }
})

test('PNG share starts during click, blocks duplicates and treats cancellation as no action', async () => {
  const pending = deferred(); let inClick = false
  const f = await fixture({ share: () => { assert.equal(inClick, true); return pending.promise } })
  try {
    const button = f.button('Chia sẻ PNG')
    await act(async () => { inClick = true; button.click(); button.click(); inClick = false })
    assert.equal(f.shares.length, 1); assert.equal(f.shares[0].files[0], f.urls.find(item => item.file.type === 'image/png').file); assert.equal(f.shares[0].url, undefined)
    assert.equal(f.button('Chia sẻ qua Zalo').disabled, true); assert.equal(document.querySelector('button[aria-label="Đóng báo cáo số khách"]').disabled, true)
    await act(async () => pending.reject(Object.assign(Error('cancel'), { name: 'AbortError' })))
    assert.equal(document.querySelector('[role=alert]'), null); assert.equal(document.querySelector('[data-system-feedback]'), null); assert.deepEqual(f.downloads, [])
    assert.equal(f.button('Chia sẻ PNG').disabled, false); assert.equal(f.button('Chia sẻ qua Zalo').disabled, false)
  } finally { await f.dispose() }
})

test('PDF sharing still sends PDF and reports handoff without claiming delivery', async () => {
  const f = await fixture()
  try {
    await act(async () => f.button('Chia sẻ qua Zalo').click())
    assert.equal(f.shares[0].files[0].type, 'application/pdf'); assert.equal(document.querySelector('[data-system-feedback]').textContent, 'Đã chuyển file sang ứng dụng chia sẻ.'); assert.deepEqual(f.downloads, [])
  } finally { await f.dispose() }
})

test('per-format capability retains PNG download when only PDF share is supported', async () => {
  const f = await fixture({ canShare: data => data.files[0].type === 'application/pdf' })
  try {
    assert.equal(f.button('Chia sẻ PNG'), undefined); assert.ok(f.button('Chia sẻ qua Zalo')); assert.ok(f.download('png')); assert.match(document.body.textContent, /Tải PNG rồi đính kèm trong Zalo/)
    await act(async () => f.download('png').click()); assert.equal(f.downloads.length, 1); assert.equal(f.shares.length, 0)
  } finally { await f.dispose() }
})

test('share failures use shared feedback and retain download without auto-downloading', async () => {
  const f = await fixture({ share: () => { throw Object.assign(Error('denied'), { name: 'NotAllowedError' }) } })
  try {
    await act(async () => f.button('Chia sẻ PNG').click())
    assert.match(document.querySelector('.error-box[role=alert]').textContent, /Không mở được chia sẻ PNG.*tải PNG/)
    assert.ok(f.download('png')); assert.equal(f.button('Chia sẻ PNG').disabled, false); assert.deepEqual(f.downloads, [])
  } finally { await f.dispose() }
})

for (const failed of ['png', 'pdf']) {
  test(`${failed.toUpperCase()} failure preserves other format and retries only failed report`, async () => {
    let failures = 1
    const f = await fixture({ prepare: (format, _filters, _options, blobs) => format === failed && failures-- > 0 ? Promise.reject(Error(`Không tạo được ${failed.toUpperCase()}`)) : Promise.resolve(blobs[format]) })
    try {
      const ready = failed === 'png' ? 'pdf' : 'png', readyUrl = f.download(ready).href
      assert.match(document.querySelector('[role=alert]').textContent, new RegExp(failed.toUpperCase())); assert.equal(f.download(failed), null)
      await act(async () => f.button(`Thử tạo lại ${failed.toUpperCase()}`).click())
      assert.deepEqual(f.requests.map(item => item.format), ['pdf', 'png', failed]); assert.equal(f.download(ready).href, readyUrl); assert.ok(f.download(failed)); assert.equal(document.querySelector('[role=alert]'), null); assert.deepEqual(f.revoked, [])
    } finally { await f.dispose() }
  })
}

test('filter changes abort obsolete reports, hide stale files and discard late completion', async () => {
  const oldPng = deferred(), newPdf = deferred(), newPng = deferred(), next = { ...filters, date_from: '2026-09-01', total_amount: 125000 }
  const f = await fixture({ prepare: (format, scope, _options, blobs) => scope === filters ? (format === 'png' ? oldPng.promise : Promise.resolve(blobs.pdf)) : format === 'png' ? newPng.promise : newPdf.promise })
  try {
    assert.ok(f.download('pdf')); await f.render(next)
    assert.equal(f.download('pdf'), null); assert.equal(f.download('png'), null); assert.ok(f.requests.slice(0, 2).every(request => request.signal.aborted)); assert.deepEqual(f.revoked, ['blob:prepared-1'])
    await act(async () => oldPng.resolve(f.blobs.png)); assert.equal(f.urls.length, 1, 'obsolete PNG must not create a URL')
    await act(async () => { newPdf.resolve(f.blobs.pdf); newPng.resolve(f.blobs.png) })
    assert.deepEqual(f.requests.slice(2).map(request => request.filters), [next, next]); assert.equal(f.download('pdf').href, 'blob:prepared-2'); assert.equal(f.download('png').href, 'blob:prepared-3')
  } finally { await f.dispose() }
})

test('closing during generation aborts reads and late files never create URLs or share', async () => {
  const pdf = deferred(), png = deferred(), f = await fixture({ prepare: format => format === 'png' ? png.promise : pdf.promise })
  try {
    await act(async () => document.querySelector('button[aria-label="Đóng báo cáo số khách"]').click()); assert.equal(f.closes(), 1)
    await f.unmount(); assert.ok(f.requests.every(request => request.signal.aborted))
    await act(async () => { pdf.resolve(f.blobs.pdf); png.resolve(f.blobs.png) }); assert.deepEqual(f.urls, []); assert.deepEqual(f.shares, []); assert.equal(document.body.style.overflow, '')
  } finally { await f.dispose() }
})

test('late share result cannot show feedback in a newer filter session', async () => {
  const pending = deferred(), f = await fixture({ share: () => pending.promise })
  try {
    await act(async () => f.button('Chia sẻ PNG').click()); await f.render({ ...filters, employee: 'Lan' }); await act(async () => pending.resolve())
    assert.equal(document.querySelector('[data-system-feedback]'), null); assert.equal(f.button('Chia sẻ PNG').disabled, false)
  } finally { await f.dispose() }
})
