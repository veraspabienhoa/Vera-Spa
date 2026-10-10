import test from 'node:test'
import assert from 'node:assert/strict'
import { createRequire } from 'node:module'
import { fileURLToPath } from 'node:url'
import { build } from 'esbuild'
import React, { act } from 'react'
import { JSDOM } from 'jsdom'

const built = await build({
  entryPoints: [fileURLToPath(new URL('../src/pages/PurchasePage.jsx', import.meta.url))],
  bundle: true, write: false, metafile: true, platform: 'node', format: 'cjs', jsx: 'automatic',
  external: ['react', 'react-dom', 'react/jsx-runtime', 'lucide-react'],
  loader: { '.css': 'empty' },
  plugins: [{ name: 'purchase-action-boundaries', setup(builder) {
    builder.onResolve({ filter: /\/lib\/(api|systemDialogs)$/ }, ({ path }) => ({
      path: path.split('/').at(-1), namespace: 'fixture',
    }))
    builder.onLoad({ filter: /.*/, namespace: 'fixture' }, ({ path }) => ({
      contents: path === 'api'
        ? 'export const veraApi = new Proxy({}, { get: (_, method) => (...args) => window.purchaseFixture[method](...args) });'
        : 'export const confirmDialog = (...args) => window.purchaseFixture.confirm(...args);',
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

async function fixture({ rows = purchaseRows, permissions = {}, user = { role: 'admin', id: 'account-a' }, embedded = false } = {}) {
  const dom = new JSDOM('<body><div id="root"></div></body>', { url: 'https://example.test', pretendToBeVisual: true })
  const values = {
    window: dom.window, document: dom.window.document, navigator: dom.window.navigator,
    File: dom.window.File, URL: dom.window.URL, IS_REACT_ACT_ENVIRONMENT: true,
  }
  const saved = Object.fromEntries(Object.keys(values).map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]))
  for (const [key, value] of Object.entries(values)) Object.defineProperty(globalThis, key, { value, configurable: true })

  const reads = [], exports = [], imports = [], audits = [], deletes = [], confirmations = []
  dom.window.purchaseFixture = {
    purchases: async params => {
      reads.push(params)
      return { rows, permissions, start: '2026-10-01', end: '2026-10-31' }
    },
    exportPurchases: async params => { exports.push(params) },
    importPurchases: async (file, mode) => { imports.push({ file, mode }); return { source_rows: rows.length, inserted: rows.length, skipped: 0, total: rows.reduce((total, row) => total + row.amount, 0) } },
    purchaseAudit: async () => { audits.push(true); return { rows: [] } },
    deletePurchase: async (id, revision) => { deletes.push({ id, revision }) },
    confirm: async message => { confirmations.push(message); return true },
  }
  dom.window.HTMLDialogElement.prototype.showModal = function () { this.open = true }
  dom.window.HTMLDialogElement.prototype.close = function () { this.open = false }
  const mod = { exports: {} }
  new Function('require', 'module', 'exports', built.outputFiles[0].text)(createRequire(import.meta.url), mod, mod.exports)
  // Import after installing the DOM so React detects support for input events.
  const { createRoot } = await import('react-dom/client')
  const root = createRoot(document.querySelector('#root'))
  let mounted = true
  const unmount = async () => {
    if (mounted) { await act(async () => root.unmount()); mounted = false }
  }
  const render = async user => act(async () => root.render(React.createElement(mod.exports.default, { user, embedded })))
  await render(user)
  return {
    dom, reads, exports, imports, audits, deletes, confirmations, unmount, render,
    action: name => document.querySelector(`[data-ui-key="purchases:${name}"]`),
    preview: () => document.querySelector('dialog.purchase-modal'),
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

test('purchase page no longer bundles the PNG capture engine', () => {
  assert.ok(!Object.keys(built.metafile.inputs).some(path => path.includes('clipboardImage')))
})

const adminActions = ['create', 'refresh', 'history', 'edit', 'delete', 'import-append', 'import-replace', 'export']
const actionNames = () => [...document.querySelectorAll('[data-ui-key="purchases:actions"] button')]
  .map(button => button.dataset.uiKey.replace('purchases:', ''))
function assertNoPng() {
  assert.equal(document.querySelector('[data-ui-key="purchases:download-png"]'), null)
  assert.equal(document.querySelector('[data-ui-key="purchases:share-png"]'), null)
  assert.equal(document.querySelector('.purchase-png-capture'), null)
  assert.doesNotMatch(document.body.textContent, /Tải PNG|Share PNG|Chia sẻ PNG/)
}

for (const embedded of [false, true]) {
  test(`purchase PNG actions are absent in the ${embedded ? 'embedded report' : 'standalone page'} while admin actions remain`, async () => {
    const f = await fixture({ embedded })
    try {
      assert.deepEqual(actionNames(), adminActions)
      assertNoPng()
      assert.equal(document.querySelectorAll('.purchase-table table').length, 1)
      assert.equal(f.action('edit').disabled, true)
      assert.equal(f.action('delete').disabled, true)
      await f.setItemFilter('KHĂN')
      assert.match(document.querySelector('.purchase-filter-total').textContent, /140\.000đ/)
      await act(async () => document.querySelector('input[aria-label="Chọn Khăn mặt"]').click())
      assert.equal(f.action('edit').disabled, false)
      assert.equal(f.action('delete').disabled, false)
      await act(async () => f.action('export').click())
      assert.deepEqual(f.exports, [{ preset: 'this_month' }])
      await act(async () => f.action('refresh').click())
      assert.deepEqual(f.reads, [{ preset: 'this_month' }, { preset: 'this_month' }])
      assert.equal(f.action('edit').disabled, true, 'refresh still clears selection')
      assertNoPng()
    } finally { await f.dispose() }
  })
}

for (const permissions of [{}, { purchase_create: true, purchase_edit: true, purchase_delete: true }]) {
  test(`purchase action permissions remain intact with ${Object.keys(permissions).length ? 'explicit grants' : 'read-only access'}`, async () => {
    const f = await fixture({ permissions, user: { role: 'quanly', id: 'manager' } })
    try {
      const expected = Object.keys(permissions).length ? ['create', 'refresh', 'edit', 'delete', 'export'] : ['refresh', 'export']
      assert.deepEqual(actionNames(), expected)
      assertNoPng()
      await act(async () => f.action('export').click())
      assert.deepEqual(f.exports, [{ preset: 'this_month' }])
    } finally { await f.dispose() }
  })
}

test('purchase create, edit, history and deletion still use their original actions and dialogs', async () => {
  const f = await fixture()
  try {
    await act(async () => f.action('create').click())
    assert.match(f.preview().textContent, /Nhập mua hàng/)
    await act(async () => f.preview().querySelector('button[aria-label="Đóng"]').click())
    await act(async () => document.querySelector('input[aria-label="Chọn Khăn mặt"]').click())
    await act(async () => f.action('edit').click())
    assert.match(f.preview().textContent, /Sửa mua hàng/)
    assert.ok([...f.preview().querySelectorAll('input')].some(input => input.value === 'Khăn mặt'))
    await act(async () => f.preview().querySelector('button[aria-label="Đóng"]').click())
    await act(async () => f.action('history').click())
    assert.deepEqual(f.audits, [true])
    assert.match(f.preview().textContent, /Lịch sử mua hàng/)
    await act(async () => f.preview().querySelector('button[aria-label="Đóng"]').click())
    await act(async () => f.action('delete').click())
    assert.deepEqual(f.confirmations, ['Xóa 1 dòng đã chọn?'])
    assert.deepEqual(f.deletes, [{ id: 1, revision: undefined }])
    assertNoPng()
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
    assert.equal(document.querySelectorAll('tbody tr').length, 100, 'only the visible page is mounted')
    assertNoPng()
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

test('both purchase import buttons keep their file picker mode and replacement confirmation', async () => {
  const f = await fixture()
  try {
    const input = document.querySelector('input[type="file"]'), opened = []
    input.click = () => opened.push(true)
    for (const [action, mode] of [['import-append', 'append'], ['import-replace', 'replace']]) {
      await act(async () => f.action(action).click())
      const file = new File(['synthetic'], `${mode}.xlsx`)
      Object.defineProperty(input, 'files', { value: [file], configurable: true })
      await act(async () => input.dispatchEvent(new window.Event('change', { bubbles: true })))
      assert.deepEqual(f.imports.at(-1), { file, mode })
    }
    assert.equal(opened.length, 2)
    assert.deepEqual(f.confirmations, ['Thay toàn bộ dữ liệu Nhập mua bằng file được chọn? Dữ liệu cũ được lưu trong lịch sử.'])
    assertNoPng()
  } finally { await f.dispose() }
})

test('same-grant purchase account switches clear rows, selection and paging before the next read resolves', async () => {
  const next = deferred(), f = await fixture({ rows: manyPurchases(205) })
  try {
    await act(async () => displayTable().querySelector('input').click())
    await act(async () => pageButton('Trang sau').click())
    f.dom.window.purchaseFixture.purchases = () => next.promise
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
