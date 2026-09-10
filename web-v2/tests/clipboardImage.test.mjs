import test from 'node:test'
import assert from 'node:assert/strict'
import { copyPngToClipboard } from '../src/lib/clipboardImage.js'

function replaceGlobal(t, key, value) {
  const original = Object.getOwnPropertyDescriptor(globalThis, key)
  Object.defineProperty(globalThis, key, { configurable: true, value })
  t.after(() => {
    if (original) Object.defineProperty(globalThis, key, original)
    else delete globalThis[key]
  })
}

function clipboard(t, write) {
  replaceGlobal(t, 'navigator', { clipboard: { write } })
  replaceGlobal(t, 'ClipboardItem', class { constructor(data) { this.data = data } })
}

test('starts clipboard write in the click turn before the image request completes', async t => {
  let loading = false, writes = 0, copied
  const png = new Blob(['png'], { type: 'image/png' })
  clipboard(t, async items => {
    writes++
    assert.equal(loading, false)
    assert.deepEqual(Object.keys(items[0].data), ['image/png'])
    copied = await items[0].data['image/png']
  })
  await copyPngToClipboard(async () => { loading = true; return png })
  assert.equal(writes, 1)
  assert.equal(copied, png)
})

test('unsupported clipboard does not fetch or save an image', async t => {
  replaceGlobal(t, 'navigator', {})
  let loads = 0
  await assert.rejects(copyPngToClipboard(() => { loads++ }), /chưa hỗ trợ copy ảnh/)
  assert.equal(loads, 0)
})

test('fetch and invalid PNG failures reach the caller without another action', async t => {
  clipboard(t, async items => { await items[0].data['image/png'] })
  await assert.rejects(copyPngToClipboard(async () => { throw new Error('API unavailable') }), /API unavailable/)
  await assert.rejects(copyPngToClipboard(async () => new Blob(['html'], { type: 'text/html' })), /ảnh bảng tua hợp lệ/)
})

test('clipboard denial is reported and does not fall back to saving', async t => {
  clipboard(t, async () => { throw new DOMException('Denied', 'NotAllowedError') })
  await assert.rejects(copyPngToClipboard(async () => new Blob(['png'], { type: 'image/png' })), { name: 'NotAllowedError' })
})
