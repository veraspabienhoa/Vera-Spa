import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/PurchasePage.jsx', import.meta.url))],
  bundle: true, write: false, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react-dom', 'react/jsx-runtime', 'lucide-react'],
  loader: { '.css': 'empty' },
  plugins: [{ name: 'purchase-png-boundaries', setup(builder) {
    builder.onResolve({ filter: /\/lib\/(api|clipboardImage)$/ }, ({ path }) => ({
      path: path.split('/').at(-1), namespace: 'fixture',
    }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
      contents: path === 'api'
        ? 'export const veraApi = new Proxy({}, { get: (_, method) => (...args) => window.purchasePngFixture[method](...args) });'
        : 'export const elementToPngBlob = (...args) => window.purchasePngFixture.capture(...args);',
      loader: 'js',
    }))
  } }],
})

const purchaseRows = [
  { id: 1, purchase_date: '2026-10-01', item: 'Khăn mặt', quantity: 2, unit_price: 25000, amount: 50000, note: 'Quầy lễ tân', entered_at: '2026-10-01T02:00:00Z', entered_by: 'Admin' },
  { id: 2, purchase_date: '2026-10-02', item: 'Dầu massage', quantity: 1, unit_price: 200000, amount: 200000, note: 'Phòng 2', entered_at: '2026-10-02T03:00:00Z', entered_by: 'Admin' },
  { id: 3, purchase_date: '2026-10-03', item: 'Khăn tắm', quantity: 3, unit_price: 30000, amount: 90000, note: 'Phòng 3', entered_at: '2026-10-03T04:00:00Z', entered_by: 'Admin' },
]

function deferred() {
  let resolve
  const promise = new Promise(done => { resolve = done })
  return { promise, resolve }
}

async function fixture({ pendingCapture, share, canShare, rows = purchaseRows, captureError } = {}) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
  const values = {
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    File: dom.window.File, URL: dom.window.URL, IS_REACT_ACT_ENVIRONMENT: true,
  }
  const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { value, configurable: true })

  const captures = [], downloads = [], objectUrls = [], revoked = [], timers = [], reads = [], exports = [], imports = []
  const png = new dom.window.Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10])], { type: 'image/png' })
  dom.window.purchasePngFixture = {
    purchases: async params => {
      reads.push(params)
      return { rows, permissions: {}, start: '2026-10-01', end: '2026-10-31' }
    },
    exportPurchases: async params => { exports.push(params) },
    importPurchases: async (file, mode) => { imports.push({ file, mode }); return { source_rows: rows.length, inserted: rows.length, skipped: 0, total: rows.reduce((total, row) => total + row.amount, 0) } },
    // jsdom cannot render a canvas. Keep the page, filters, File construction,
    // download/share handlers and modal real; replace only the capture engine.
    capture: table => {
      captures.push({ table, snapshot: table.cloneNode(true) })
      return captureError ? Promise.reject(captureError) : pendingCapture?.promise || Promise.resolve(png)
    },
  }
  URL.createObjectURL = file => {
    const url = `blob:purchase-png-${objectUrls.length + 1}`
    objectUrls.push({ url, file })
    return url
  }
  URL.revokeObjectURL = url => revoked.push(url)
  dom.window.HTMLAnchorElement.prototype.click = function () {
    downloads.push({ href: this.href, filename: this.download })
  }
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true }
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false }
  const setTimeout = dom.window.setTimeout.bind(dom.window)
  dom.window.setTimeout = (callback, delay, ...args) => {
    if (delay === 60000) { timers.push({ callback, delay }); return timers.length }
    return setTimeout(callback, delay, ...args)
  }
  if (share) navigator.share = share
  if (canShare) navigator.canShare = canShare

  const mod = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
  // Import after installing the DOM so React detects support for input events.
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('#root'))
  let mounted = true
  const unmount = async () => {
    if (mounted) { await act(async () => root.unmount()); mounted = false }
  }
  const render = async user => act(async () => root.render(React.createElement(mod.exports.default, { user })))
  await render({ role: 'admin', id: 'account-a' })
  return {
    dom, captures, downloads, objectUrls, revoked, timers, reads, exports, imports, png, unmount, render,
    action: name => document.querySelector(`[data-ui-key="purchases:${name}"]`),
    preview: () => document.querySelector('dialog.purchase-modal'),
    shareButton: () => [...document.querySelectorAll('dialog footer button')].find(button => button.textContent.includes('Chia sẻ ảnh')),
    setItemFilter: async value => {
      const input = document.querySelector('input[placeholder="Tìm hàng hóa"]')
      await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, 'value').set.call(input, value)
        input.dispatchEvent(new dom.window.Event('input', { bubbles: true }))
      })
    },
    dispose: async () => {
      try { await unmount() }
      finally {
        dom.window.close()
        for (const [key, descriptor] of Object.entries(saved)) {
          if (descriptor) Object.defineProperty(globalThis, key, descriptor)
          else delete globalThis[key]
        }
      }
    },
  }
}

test('Download PNG captures the currently filtered table, then saves a PNG and cleans its download URL', async () => {
  const capture = deferred()
  const f = await fixture({ pendingCapture: capture })
  try {
    await f.setItemFilter('KHĂN')
    await act(async () => document.querySelector('input[aria-label="Chọn Khăn mặt"]').click())
    const visibleTable = document.querySelector('.purchase-table table')
    assert.equal(visibleTable.tBodies[0].rows.length, 2)
    await act(async () => f.action('download-png').click())

    assert.equal(f.captures.length, 1)
    assert.notEqual(f.captures[0].table, visibleTable, 'capture uses an on-demand complete snapshot, not the display page')
    const captured = f.captures[0].snapshot
    assert.deepEqual([...captured.tBodies[0].rows].map(row => row.cells[2].textContent), ['Khăn mặt', 'Khăn tắm'], 'capture includes all filtered rows, not just checked rows')
    assert.match(captured.caption.textContent, /01-10-2026 – 31-10-2026/)
    assert.match(captured.caption.textContent, /Tổng mua: 140\.000đ/)
    assert.doesNotMatch(captured.textContent, /Dầu massage/)
    assert.equal(captured.querySelectorAll('[data-snapshot-ignore]').length, 3, 'selection header and cells stay marked for the capture engine to exclude')
    assert.equal(f.action('download-png').disabled, true)
    assert.equal(f.action('share-png').disabled, true)
    assert.deepEqual(f.downloads, [], 'the page must finish capturing before saving')
    assert.deepEqual(f.objectUrls, [])

    await act(async () => capture.resolve(f.png))
    assert.equal(f.downloads.length, 1)
    const { file, url } = f.objectUrls[0]
    assert.ok(file instanceof File)
    assert.equal(file.type, 'image/png')
    assert.equal(file.size, f.png.size)
    assert.match(file.name, /^nhap-mua-\d{4}-\d{2}-\d{2}\.png$/)
    assert.deepEqual(f.downloads[0], { href: url, filename: file.name })
    assert.equal(f.preview(), null)
    assert.equal(f.action('download-png').disabled, false)
    assert.deepEqual(f.reads, [{ preset: 'this_month' }], 'client-side capture does not reload or export server data')
    assert.deepEqual(f.revoked, [], 'allow the browser to consume the download URL before revocation')
    assert.equal(f.timers.length, 1)
    assert.equal(f.timers[0].delay, 60000)
    f.timers[0].callback()
    assert.deepEqual(f.revoked, [url])
  } finally { await f.dispose() }
})

test('Share PNG opens a prepared preview before native file sharing, and closing it revokes the preview URL', async () => {
  const capture = deferred(), shares = [], supportChecks = []
  const f = await fixture({
    pendingCapture: capture,
    share: data => { shares.push(data); return Promise.resolve() },
    canShare: data => { supportChecks.push(data); return true },
  })
  try {
    await f.setItemFilter('Dầu')
    await act(async () => f.action('share-png').click())
    assert.equal(f.captures.length, 1)
    assert.equal(f.captures[0].snapshot.tBodies[0].rows.length, 1)
    assert.match(f.captures[0].snapshot.textContent, /Dầu massage/)
    assert.equal(f.preview(), null)
    assert.deepEqual(shares, [])

    await act(async () => capture.resolve(f.png))
    const preview = f.preview()
    const { file, url } = f.objectUrls[0]
    assert.equal(preview.open, true)
    assert.equal(preview.querySelector('img').src, url)
    assert.equal(preview.querySelector('img').alt, 'Bảng Nhập mua theo bộ lọc hiện tại')
    assert.deepEqual(shares, [], 'preparing the image never opens a native share sheet')
    assert.deepEqual(supportChecks, [])
    assert.deepEqual(f.downloads, [])

    await act(async () => {
      f.shareButton().click()
      assert.equal(shares.length, 1, 'native sharing starts in the explicit share-button click')
    })
    assert.deepEqual(supportChecks, [{ files: [file] }])
    assert.deepEqual(shares, [{ files: [file], title: 'Nhập mua · VERA SPA' }])
    assert.equal(file.type, 'image/png')
    assert.equal(f.captures.length, 1, 'share reuses the prepared file instead of capturing again')
    assert.deepEqual(f.downloads, [])
    assert.deepEqual(f.revoked, [])
    assert.equal(document.querySelector('[role="alert"]'), null)

    await act(async () => preview.querySelector('button[aria-label="Đóng"]').click())
    assert.equal(f.preview(), null)
    assert.deepEqual(f.revoked, [url])
    await f.unmount()
    assert.deepEqual(f.revoked, [url], 'closed previews are not revoked twice on unmount')
  } finally { await f.dispose() }
})

for (const unsupported of ['share unavailable', 'canShare unavailable', 'file sharing unsupported']) {
  test(`Share PNG downloads the prepared file when ${unsupported}`, async () => {
    const shares = []
    const f = await fixture({
      share: unsupported === 'share unavailable' ? undefined : data => { shares.push(data); return Promise.resolve() },
      canShare: unsupported === 'canShare unavailable' ? undefined : () => false,
    })
    try {
      await act(async () => f.action('share-png').click())
      const { file, url: previewUrl } = f.objectUrls[0]
      assert.ok(f.preview())
      assert.deepEqual(f.downloads, [], 'fallback also waits for the second, explicit click')
      await act(async () => f.shareButton().click())

      assert.deepEqual(shares, [])
      assert.equal(f.captures.length, 1)
      assert.equal(f.objectUrls.length, 2)
      assert.equal(f.objectUrls[1].file, file, 'fallback saves the exact file shown in the preview')
      assert.deepEqual(f.downloads, [{ href: f.objectUrls[1].url, filename: file.name }])
      assert.equal(f.preview(), null)
      assert.match(document.querySelector('[role="status"]').textContent, /chưa hỗ trợ chia sẻ file.*Đã tải PNG/)
      assert.equal(document.querySelector('[role="alert"]'), null)
      assert.deepEqual(f.revoked, [previewUrl])
      assert.equal(f.timers.length, 1)
      f.timers[0].callback()
      assert.deepEqual(f.revoked, [previewUrl, f.objectUrls[1].url])
    } finally { await f.dispose() }
  })
}

test('canceling native PNG sharing does not download or show an error, and unmount revokes the preview URL', async () => {
  const shares = []
  const f = await fixture({
    canShare: () => true,
    share: data => {
      shares.push(data)
      return Promise.reject(Object.assign(new Error('The user canceled sharing'), { name: 'AbortError' }))
    },
  })
  try {
    await act(async () => f.action('share-png').click())
    const { file, url } = f.objectUrls[0]
    await act(async () => f.shareButton().click())

    assert.deepEqual(shares, [{ files: [file], title: 'Nhập mua · VERA SPA' }])
    assert.deepEqual(f.downloads, [])
    assert.deepEqual(f.timers, [])
    assert.equal(f.objectUrls.length, 1, 'cancellation creates no fallback file URL')
    assert.equal(document.querySelector('[role="alert"]'), null)
    assert.equal(document.querySelector('[role="status"]'), null)
    assert.equal(f.preview().querySelector('img').src, url)
    assert.deepEqual(f.revoked, [], 'the still-open preview keeps its URL')
    await f.unmount()
    assert.equal(f.preview(), null)
    assert.deepEqual(f.revoked, [url])
  } finally { await f.dispose() }
})

test('dismissing the PNG preview with the dialog cancel event revokes its URL without saving or sharing', async () => {
  const shares = []
  const f = await fixture({ canShare: () => true, share: data => { shares.push(data); return Promise.resolve() } })
  try {
    await act(async () => f.action('share-png').click())
    const { url } = f.objectUrls[0]
    const cancel = new f.dom.window.Event('cancel', { cancelable: true })
    await act(async () => f.preview().dispatchEvent(cancel))
    assert.equal(cancel.defaultPrevented, true)
    assert.equal(f.preview(), null)
    assert.deepEqual(shares, [])
    assert.deepEqual(f.downloads, [])
    assert.deepEqual(f.revoked, [url])
  } finally { await f.dispose() }
})

const manyPurchases = count => Array.from({ length: count }, (_, index) => ({
  ...purchaseRows[0], id: index + 1, item: `Hàng ${String(index + 1).padStart(4, '0')}`, amount: 10,
}))
const purchasePager = () => document.querySelector('nav[aria-label="Phân trang mua hàng"]')
const pageButton = text => [...purchasePager().querySelectorAll('button')].find(button => button.textContent === text)
const displayTable = () => document.querySelector('.stable-data-region .purchase-table table') || document.querySelector('.purchase-table table')

test('3000 purchases mount only 100 rows, retain cross-page selections and full totals, and reset pages on filters', async () => {
  const f = await fixture({ rows: manyPurchases(3000) })
  try {
    assert.equal(document.querySelectorAll('tbody tr').length, 100, 'no hidden all-row table exists before an export')
    assert.match(document.querySelector('.purchase-filter-total').textContent, /30\.000đ/)
    assert.match(purchasePager().textContent, /Trang 1 \/ 30/)
    await act(async () => displayTable().querySelector('input').click())
    assert.equal(f.action('edit').disabled, false)
    await act(async () => pageButton('Trang sau').click())
    assert.match(displayTable().tBodies[0].rows[0].textContent, /Hàng 0101/)
    await act(async () => displayTable().querySelector('input').click())
    assert.equal(f.action('edit').disabled, true, 'selected rows on the previous page are retained')
    await act(async () => pageButton('Trang trước').click())
    assert.equal(displayTable().querySelector('input').checked, true)
    await act(async () => pageButton('Trang sau').click())
    await f.setItemFilter('Hàng 01')
    assert.equal(displayTable().tBodies[0].rows.length, 100)
    assert.match(displayTable().tBodies[0].rows[0].textContent, /Hàng 0100/)
    assert.match(document.querySelector('.purchase-filter-total').textContent, /1\.000đ/)
    assert.equal(purchasePager(), null)
    await f.setItemFilter('Hàng 0001')
    assert.equal(displayTable().tBodies[0].rows.length, 1)
    assert.equal(displayTable().querySelector('input').checked, true)
    await f.setItemFilter('')
    assert.match(purchasePager().textContent, /Trang 1 \/ 30/)
    assert.deepEqual(f.reads, [{ preset: 'this_month' }], 'display paging and local filtering issue no extra reads')
    await act(async () => f.action('export').click())
    assert.deepEqual(f.exports, [{ preset: 'this_month' }], 'Excel keeps its full date-range API export, with no page limit')
  } finally { await f.dispose() }
})

test('PNG on a later display page captures every filtered row and cleans up its temporary full table', async () => {
  const rows = manyPurchases(205).map((row, index) => ({ ...row, item: `${index < 150 ? 'Khăn' : 'Dầu'} ${row.item}` }))
  const capture = deferred()
  const f = await fixture({ rows, pendingCapture: capture })
  try {
    await f.setItemFilter('Khăn')
    await act(async () => pageButton('Trang sau').click())
    assert.equal(displayTable().tBodies[0].rows.length, 50)
    await act(async () => f.action('download-png').click())
    assert.equal(f.captures[0].snapshot.tBodies[0].rows.length, 150)
    assert.match(f.captures[0].snapshot.textContent, /Khăn Hàng 0001/)
    assert.match(f.captures[0].snapshot.textContent, /Khăn Hàng 0150/)
    assert.doesNotMatch(f.captures[0].snapshot.textContent, /Dầu/)
    assert.match(f.captures[0].snapshot.caption.textContent, /Tổng mua: 1\.500đ/)
    assert.equal(displayTable().tBodies[0].rows.length, 50, 'the visible table remains on the selected page while capturing')
    await act(async () => capture.resolve(f.png))
    assert.equal(document.querySelector('.purchase-png-capture'), null)
    assert.equal(document.querySelectorAll('tbody tr').length, 50)
    assert.match(purchasePager().textContent, /Trang 2 \/ 2/)
    assert.equal(f.downloads.length, 1)
  } finally { await f.dispose() }
})

test('failed full PNG capture reports the error without exporting a partial page or retaining full DOM', async () => {
  const f = await fixture({ rows: manyPurchases(205), captureError: new Error('Synthetic capture failure') })
  try {
    await act(async () => pageButton('Trang sau').click())
    await act(async () => f.action('download-png').click())
    assert.equal(f.captures[0].snapshot.tBodies[0].rows.length, 205)
    assert.equal(document.querySelectorAll('tbody tr').length, 100)
    assert.equal(document.querySelector('.purchase-png-capture'), null)
    assert.match(document.querySelector('[role="alert"]').textContent, /Synthetic capture failure/)
    assert.deepEqual(f.downloads, [])
    assert.match(purchasePager().textContent, /Trang 2 \/ 3/)
  } finally { await f.dispose() }
})

test('import may switch to all purchases without mounting all imported rows', async () => {
  const f = await fixture({ rows: manyPurchases(3000) })
  try {
    const file = new File(['synthetic'], 'purchases.xlsx')
    const input = document.querySelector('input[type="file"]')
    Object.defineProperty(input, 'files', { value: [file], configurable: true })
    await act(async () => input.dispatchEvent(new window.Event('change', { bubbles: true })))
    assert.deepEqual(f.imports, [{ file, mode: 'append' }])
    assert.deepEqual(f.reads, [{ preset: 'this_month' }, { preset: 'all' }])
    assert.equal(document.querySelectorAll('tbody tr').length, 100)
    assert.match(purchasePager().textContent, /Trang 1 \/ 30/)
    assert.match(document.querySelector('.purchase-filter-total').textContent, /30\.000đ/)
  } finally { await f.dispose() }
})

test('same-grant purchase account switches clear rows, selection and paging before the next read resolves', async () => {
  const next = deferred(), f = await fixture({ rows: manyPurchases(205) })
  try {
    await act(async () => displayTable().querySelector('input').click())
    await act(async () => pageButton('Trang sau').click())
    f.dom.window.purchasePngFixture.purchases = () => next.promise
    await f.render({ role: 'admin', id: 'account-b' })
    assert.doesNotMatch(displayTable().textContent, /Hàng 0101/)
    assert.match(displayTable().textContent, /Không có dữ liệu/)
    assert.equal(purchasePager(), null)
    await act(async () => next.resolve({ rows: manyPurchases(205), permissions: {} }))
    assert.match(purchasePager().textContent, /Trang 1 \/ 3/)
    assert.equal(displayTable().querySelector('input').checked, false)
    assert.equal(f.action('edit').disabled, true)
  } finally { next.resolve({ rows: [], permissions: {} }); await f.dispose() }
})
