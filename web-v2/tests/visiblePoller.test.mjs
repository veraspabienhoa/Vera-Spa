import test from 'node:test'
import assert from 'node:assert/strict'
import { createVisiblePoller } from '../src/lib/visiblePoller.js'

function fixture(load, hidden = false) {
  const doc = new EventTarget(); doc.hidden = hidden
  const tasks = new Map(); let next = 0
  const poller = createVisiblePoller(load, { document: doc, interval: 30000,
    setTimeout(fn, delay) { assert.equal(delay, 30000); tasks.set(++next, fn); return next }, clearTimeout(id) { tasks.delete(id) } })
  return { ...poller, tasks, doc, visible(value) { doc.hidden = !value; doc.dispatchEvent(new Event('visibilitychange')) } }
}
const tick = () => new Promise(r => setImmediate(r))

test('slow requests never overlap, including manual refresh and visibility changes', async () => {
  let finish, calls = 0
  const f = fixture(() => { calls++; return new Promise(resolve => { finish = resolve }) })
  assert.equal(calls, 1); assert.equal(f.tasks.size, 0)
  await f.refresh(); f.visible(false); f.visible(true)
  assert.equal(calls, 1)
  finish(); await tick(); assert.equal(f.tasks.size, 1)
  const second = f.refresh(); assert.equal(calls, 2); assert.equal(f.tasks.size, 0)
  finish(); await second; f.stop()
})

test('hidden pages skip initial requests, resume once, and stop without late rescheduling', async () => {
  let finish, calls = 0
  const f = fixture(() => { calls++; return new Promise(resolve => { finish = resolve }) }, true)
  assert.equal(calls, 0)
  f.visible(true); assert.equal(calls, 1)
  f.stop(); finish(); await tick()
  assert.equal(f.tasks.size, 0)
  f.visible(true); await f.refresh(); assert.equal(calls, 1)
})

test('errors schedule a later retry and hiding the tab clears the timer', async () => {
  let calls = 0
  const f = fixture(async () => { calls++; throw Error('temporary 503') })
  await tick(); assert.equal(f.tasks.size, 1)
  f.visible(false); assert.equal(f.tasks.size, 0)
  f.visible(true); await tick(); assert.equal(calls, 2)
  f.stop(); assert.equal(f.tasks.size, 0)
})
