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
  // A copy failure must never silently become a file download or native share.
  replaceGlobal(t, 'document', { createElement() { assert.fail('copy must not download') } })
  navigator.share = () => assert.fail('copy must not share')
}

function deferred() {
  let resolve, reject
  const promise = new Promise((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

const png = () => new Blob([new Uint8Array([137, 80, 78, 71, 13, 10, 26, 10, 0, 255])], { type: 'image/png' })
async function assertPng(actual, expected) {
  assert.equal(actual.type, 'image/png')
  assert.equal(actual.size, expected.size)
  assert.deepEqual(await actual.arrayBuffer(), await expected.arrayBuffer())
}

test('starts clipboard write in the click turn before the image request completes', async t => {
  const pending = deferred(), original = png()
  let loads = 0, writes = 0, copied
  clipboard(t, async items => {
    writes++
    assert.equal(loads, 0)
    assert.equal(items.length, 1)
    assert.deepEqual(Object.keys(items[0].data), ['image/png'])
    assert.ok(items[0].data['image/png'] instanceof Promise)
    copied = await items[0].data['image/png']
  })
  const operation = copyPngToClipboard(() => { loads++; return pending.promise })
  assert.equal(writes, 1, 'write is called synchronously from the click')
  assert.equal(loads, 0)
  await Promise.resolve()
  assert.equal(loads, 1)
  assert.equal(copied, undefined, 'write waits for the pending image')
  pending.resolve(original)
  await operation
  assert.equal(writes, 1)
  // The helper deliberately wraps PNG data in a fresh Blob. Bytes and MIME type
  // matter; requiring the source object's identity is not its API.
  await assertPng(copied, original)
})

test('unsupported clipboard does not fetch or save an image', async t => {
  let loads = 0
  clipboard(t, () => assert.fail('unsupported clipboard'))
  Object.defineProperty(globalThis, 'ClipboardItem', { configurable: true, value: undefined })
  for (const browser of [{}, { clipboard: {} }, { clipboard: { write() { assert.fail('missing ClipboardItem') } } }]) {
    Object.defineProperty(globalThis, 'navigator', { configurable: true, value: browser })
    await assert.rejects(copyPngToClipboard(() => { loads++ }), /chưa hỗ trợ copy ảnh/)
  }
  assert.equal(loads, 0)
})

test('fetch and invalid PNG failures reach the caller without another action', async t => {
  let writes = 0
  clipboard(t, async items => { writes++; await items[0].data['image/png'] })
  const unavailable = new TypeError('API unavailable')
  await assert.rejects(copyPngToClipboard(async () => { throw unavailable }), error => error === unavailable)
  for (const invalid of [new Blob(['html'], { type: 'text/html' }), new Blob([], { type: 'image/png' }), null]) {
    await assert.rejects(copyPngToClipboard(async () => invalid), /ảnh PNG hợp lệ/)
  }
  assert.equal(writes, 4, 'source failures never trigger a second write')
})

test('retains the source failure when the browser masks rejected image data as NotAllowedError', async t => {
  let writes = 0
  clipboard(t, async items => {
    writes++
    try { await items[0].data['image/png'] } catch { throw new DOMException('Item data rejected', 'NotAllowedError') }
  })
  const unavailable = new Error('API unavailable')
  await assert.rejects(copyPngToClipboard(() => Promise.reject(unavailable)), error => error === unavailable)
  assert.equal(writes, 1)
})

test('clipboard denial is reported immediately and does not retry, save or share', async t => {
  const pending = deferred(), denied = new DOMException('Denied', 'NotAllowedError')
  let writes = 0
  clipboard(t, async () => { writes++; throw denied })
  await assert.rejects(copyPngToClipboard(() => pending.promise), error => error === denied)
  assert.equal(writes, 1)
  pending.reject(new Error('late image failure'))
  await new Promise(resolve => setImmediate(resolve))
})

test('security and other write failures preserve their identity without retry', async t => {
  let writes = 0, failure
  clipboard(t, async () => { writes++; throw failure })
  for (failure of [new DOMException('Insecure context', 'SecurityError'), new DOMException('Cannot encode', 'DataError')]) {
    await assert.rejects(copyPngToClipboard(png), error => error === failure)
  }
  assert.equal(writes, 2)
})

test('legacy ClipboardItem TypeError retries once with concrete PNG and unchanged bytes', async t => {
  const original = png()
  let loads = 0, constructions = 0, copied, writes = 0
  clipboard(t, async items => { writes++; copied = items[0].data['image/png'] })
  navigator.userActivation = { isActive: true }
  Object.defineProperty(globalThis, 'ClipboardItem', { configurable: true, value: class {
    constructor(data) {
      constructions++
      if (data['image/png'] instanceof Promise) throw new TypeError('Expected Blob')
      this.data = data
    }
  } })
  await copyPngToClipboard(() => { loads++; return original })
  assert.equal(loads, 1)
  assert.equal(constructions, 2)
  assert.equal(writes, 1)
  await assertPng(copied, original)
})

test('legacy write TypeError retries once and preserves a fallback denial', async t => {
  let writes = 0
  const denied = new DOMException('Denied', 'NotAllowedError')
  clipboard(t, async items => {
    writes++
    if (items[0].data['image/png'] instanceof Promise) throw new TypeError('Expected Blob')
    throw denied
  })
  await assert.rejects(copyPngToClipboard(png), error => error === denied)
  assert.equal(writes, 2)
})

test('legacy compatibility retry stops when activation has expired while loading', async t => {
  const pending = deferred(), incompatible = new TypeError('Expected Blob')
  let writes = 0
  clipboard(t, async () => { writes++; throw incompatible })
  navigator.userActivation = { isActive: true }
  const operation = copyPngToClipboard(() => pending.promise)
  navigator.userActivation.isActive = false
  pending.resolve(png())
  await assert.rejects(operation, error => error === incompatible)
  assert.equal(writes, 1)
})
