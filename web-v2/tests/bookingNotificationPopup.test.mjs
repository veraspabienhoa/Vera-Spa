import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import { readFileSync } from 'node:fs'

const built = await build({
  stdin: { contents: `import React,{act} from 'react';import {createRoot} from 'react-dom/client';import Popup from './src/components/BookingNotificationPopup';
    const root=createRoot(document.getElementById('root'));window.act=act;window.mount=user=>act(async()=>root.render(<Popup user={user} onOpen={()=>window.opens++}/>));window.unmount=()=>act(async()=>root.unmount());`, resolveDir: process.cwd(), loader: 'jsx' },
  bundle: true, write: false, format: 'iife', jsx: 'automatic', loader: { '.css': 'empty' },
  plugins: [{ name: 'shared-feed', setup(b) {
    b.onResolve({ filter: /\/lib\/notificationFeed$/ }, () => ({ path: 'feed', namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export const subscribeNotificationFeed=fn=>{window.receive=fn;window.subscriptions++;return()=>{window.receive=null;window.stops++}};' }))
  } }],
})
const row = (id = 1) => ({ id, payload: { kind: 'live_tour_booking', tag: `booking-${id}`, title: 'Booking mới', body: 'Minh Anh | 90 PR Tiêu chuẩn | YC | 2.1' } })
const user = { id: 'account-a', role: 'nhanvien' }
async function mount(identity = user) {
  const dom = new JSDOM('<div id="root"></div>', { url: 'https://example.test', runScripts: 'dangerously', pretendToBeVisual: true })
  const w = dom.window
  w.MessageChannel = class { constructor() { this.port1 = {}; this.port2 = { postMessage: () => setTimeout(() => this.port1.onmessage?.(), 0) } } }
  w.IS_REACT_ACT_ENVIRONMENT = true; w.subscriptions = 0; w.stops = 0; w.opens = 0
  w.eval(built.outputFiles[0].text)
  await w.mount(identity)
  return dom
}
const publish = (w, rows, config = {}) => w.act(async () => w.receive({ popup: rows, settings: [{ key: 'live_tour_booking', ...config }] }))

test('booking popup uses the shared feed, avoids duplicates and preserves inbox data when dismissed', async () => {
  const dom = await mount(), w = dom.window
  try {
    await publish(w, [row(), row(), { ...row(3), payload: { kind: 'other', body: 'Unrelated' } }])
    assert.equal(w.subscriptions, 1)
    assert.equal(w.document.querySelectorAll('.booking-notification-popup').length, 1)
    assert.equal(w.document.querySelector('.booking-notification-copy strong').textContent, 'Booking mới')
    assert.equal(w.document.querySelector('.booking-notification-copy p').textContent, row().payload.body)
    await w.act(async () => w.document.querySelector('.booking-notification-close').click())
    await publish(w, [row()])
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    // Navigating/reloading the component keeps local dismissals, without marking the event read.
    await w.mount({}); await w.mount(user)
    await publish(w, [row(), row(2)])
    assert.equal(w.document.querySelector('.booking-notification-copy strong').textContent, 'Booking mới')
    await w.act(async () => w.document.querySelector('.booking-notification-open').click())
    assert.equal(w.opens, 1)
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
  } finally { await w.unmount(); w.close() }
})

test('popup respects channel settings, read state and account changes', async () => {
  const dom = await mount(), w = dom.window
  try {
    await publish(w, [row()], { channel_enabled: { popup: false } })
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    await publish(w, [row()], { enabled: false })
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    await publish(w, [{ ...row(), read_at: '2026-09-27' }])
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    await publish(w, [row()], { channel_enabled: { push: false } })
    assert.ok(w.document.querySelector('.booking-notification-popup'))
    await w.act(async () => w.dispatchEvent(new w.CustomEvent('vera-notification-settings-changed', { detail: { key: 'live_tour_booking', enabled: false } })))
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    await publish(w, [row()])
    await w.act(async () => w.document.querySelector('.booking-notification-close').click())
    await w.mount({ id: 'account-b', role: 'nhanvien' })
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    await publish(w, [row()])
    assert.ok(w.document.querySelector('.booking-notification-popup'), 'dismissals must not cross accounts')
    await publish(w, [])
    assert.equal(w.document.querySelector('.booking-notification-popup'), null)
    await w.mount({ ...user, must_change_password: true })
    assert.equal(w.receive, null)
  } finally { await w.unmount(); w.close() }
})

test('booking popup is present on Live Tour and excluded from the generic popup renderer', () => {
  const shell = readFileSync('src/components/AppShell.jsx', 'utf8')
  assert.match(shell, /<BookingNotificationPopup key=/)
  assert.doesNotMatch(shell, /showPageNotifications\s*&&\s*<BookingNotificationPopup/)
  const generic = readFileSync('src/components/PopupNotifications.jsx', 'utf8')
  assert.ok(generic.includes("item.payload?.kind !== 'live_tour_booking'"))
})
