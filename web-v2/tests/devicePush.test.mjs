import test from 'node:test'
import assert from 'node:assert/strict'
import { build } from 'esbuild'
import { JSDOM } from 'jsdom'
import vm from 'node:vm'
import { readFileSync } from 'node:fs'

const bundle = await build({ stdin: { contents: "import * as push from './src/lib/pushNotifications';window.push=push", resolveDir: process.cwd() },
  bundle: true, write: false, format: 'iife', define: { 'import.meta.env.BASE_URL': '"/"' },
  plugins: [{ name: 'api', setup(b) {
    b.onResolve({ filter: /^\.\/api$/ }, () => ({ path: 'api', namespace: 'mock' }))
    b.onLoad({ filter: /.*/, namespace: 'mock' }, () => ({ contents: 'export const veraApi=window.api;' }))
  } }] })
const code = bundle.outputFiles[0].text
async function device(t, { ios = false, standalone = true, permission = 'granted', register, remove } = {}) {
  const dom = new JSDOM('', { url: 'https://app.veraspa.vn/', runScripts: 'dangerously' })
  t.after(() => dom.window.close())
  const w = dom.window, calls = { subscribed: 0, registered: 0, removed: 0, prompts: 0 }
  let subscription = null
  const cache = new Map()
  w.Response = Response
  w.caches = { open: async () => ({ put: async (key, response) => cache.set(key, await response.json()) }) }
  w.matchMedia = () => ({ matches: standalone })
  Object.defineProperty(w.navigator, 'userAgent', { value: ios ? 'iPhone' : 'Android Chrome' })
  w.PushManager = class {}
  w.Notification = { permission, requestPermission: async () => { calls.prompts++; return w.Notification.permission } }
  const registration = { getNotifications: async () => [], pushManager: {
    getSubscription: async () => subscription,
    subscribe: async options => {
      calls.subscribed++
      subscription = { endpoint: `https://push.example/${calls.subscribed}`, options,
        toJSON() { return { endpoint: this.endpoint, keys: { p256dh: 'key', auth: 'auth' } } },
        unsubscribe: async () => { subscription = null; return true } }
      return subscription
    },
  } }
  Object.defineProperty(w.navigator, 'serviceWorker', { value: { register: async () => registration } })
  w.api = { pushConfig: async () => ({ enabled: true, public_key: 'AQID' }),
    registerPushSubscription: async value => { calls.registered++; if (register) await register(value) },
    unregisterPushSubscription: async value => { calls.removed++; if (remove) await remove(value) },
  }
  w.eval(code)
  await w.push.setPushAccount('account-a')
  return { w, calls, cache }
}

for (const ios of [false, true]) test(`explicit device off survives focus and reload, ios=${ios}`, async t => {
  const { w, calls, cache } = await device(t, { ios })
  assert.equal((await w.push.enablePushNotifications()).subscribed, true)
  await w.push.disablePushNotifications()
  await Promise.all([w.push.ensureGrantedPushSubscription(), w.push.syncExistingPushSubscription()])
  assert.equal(calls.subscribed, 1)
  assert.equal(calls.registered, 1)
  assert.equal(cache.get('/__vera_push_device__').enabled, false)
  w.eval(code)
  await w.push.setPushAccount('account-a')
  assert.equal((await w.push.ensureGrantedPushSubscription()).subscribed, false)
  assert.equal(calls.subscribed, 1)
  assert.equal((await w.push.enablePushNotifications()).subscribed, true)
  assert.equal(calls.subscribed, 2)
})

test('iPhone browser gives Home Screen guidance without requesting permission', async t => {
  const { w, calls } = await device(t, { ios: true, standalone: false })
  assert.equal(w.push.getPushSupport().needsHomeScreen, true)
  await assert.rejects(w.push.enablePushNotifications(), /Màn hình chính/)
  assert.equal(calls.prompts, 0)
})

test('denied permission cannot claim the device is subscribed', async t => {
  const { w, calls } = await device(t, { permission: 'denied' })
  await assert.rejects(w.push.enablePushNotifications(), /bị chặn/)
  assert.equal((await w.push.readPushState()).subscribed, false)
  assert.equal(calls.registered, 0)
})

test('concurrent sync coalesces and opt-out wins over a delayed registration', async t => {
  let release, started
  const reached = new Promise(resolve => { started = resolve })
  const pending = new Promise(resolve => { release = resolve })
  const { w, calls, cache } = await device(t, { register: async () => { started(); await pending } })
  const first = w.push.ensureGrantedPushSubscription()
  const second = w.push.ensureGrantedPushSubscription()
  await reached
  const off = w.push.disablePushNotifications()
  release()
  await Promise.all([first, second, off])
  assert.equal(calls.registered, 1)
  assert.equal((await w.push.readPushState()).subscribed, false)
  assert.equal(cache.get('/__vera_push_device__').enabled, false)
})

test('API cleanup failure still removes browser subscription and leaves off preference', async t => {
  const { w, cache } = await device(t, { remove: async () => { throw Error('offline') } })
  await w.push.enablePushNotifications()
  assert.equal((await w.push.disablePushNotifications()).subscribed, false)
  assert.equal(cache.get('/__vera_push_device__').enabled, false)
  assert.equal(w.push.devicePushEnabled(), false)
})

test('account switch blocks old messages before registering the new owner', async t => {
  const { w, calls, cache } = await device(t)
  await w.push.enablePushNotifications()
  await w.push.setPushAccount('account-b')
  assert.equal(cache.get('/__vera_push_device__').enabled, false)
  await w.push.ensureGrantedPushSubscription()
  assert.equal(cache.get('/__vera_push_device__').owner, 'account-b')
  assert.equal(calls.subscribed, 2)
  await w.push.setPushAccount('')
  assert.equal(cache.get('/__vera_push_device__').enabled, false)
  assert.equal((await w.push.readPushState()).subscribed, false)
})

test('turning off one device does not disable a second device', async t => {
  const a = await device(t), b = await device(t)
  await a.w.push.enablePushNotifications(); await b.w.push.enablePushNotifications()
  await a.w.push.disablePushNotifications()
  assert.equal((await b.w.push.readPushState()).subscribed, true)
})

const worker = readFileSync('public/sw.js', 'utf8')
for (const [name, control, recipient, expected] of [
  ['enabled owner', { enabled: true, owner: 'a' }, 'a', 1],
  ['device off', { enabled: false, owner: 'a' }, 'a', 0],
  ['wrong account', { enabled: true, owner: 'b' }, 'a', 0],
  ['signed out', { enabled: false, owner: '' }, 'a', 0],
  ['unclaimed old message', { enabled: true, owner: 'a' }, undefined, 0],
]) test(`background service worker respects ${name}`, async () => {
  const handlers = {}, shown = [], messages = []
  let task
  const self = { location: { origin: 'https://app.veraspa.vn' }, addEventListener: (name, fn) => { handlers[name] = fn },
    registration: { showNotification: async (...args) => shown.push(args) },
    clients: { matchAll: async () => [{ postMessage: data => messages.push(data) }] } }
  vm.runInNewContext(worker, { self, URL, caches: { open: async () => ({ match: async () => ({ json: async () => control }) }) } })
  handlers.push({ data: { json: () => ({ recipient_id: recipient, notification_id: '7', title: 'Test', body: 'Full text', tag: 'event' }) }, waitUntil: promise => { task = promise } })
  await task
  assert.equal(shown.length, expected)
  if (expected) {
    assert.equal(shown[0][1].data.notificationId, '7')
    assert.equal(messages[0].type, 'vera-notification-received')
  }
})

test('Menu switch enables and disables this device and follows shared state', async () => {
  const rendered = await build({stdin:{contents:"import React from 'react';import {createRoot} from 'react-dom/client';import Menu from './src/components/DevicePushMenu';window.mount=()=>createRoot(document.getElementById('root')).render(<Menu/>);",resolveDir:process.cwd(),loader:'jsx'},bundle:true,write:false,format:'iife',jsx:'automatic',loader:{'.css':'empty'},plugins:[{name:'push-menu',setup(b){b.onResolve({filter:/\/lib\/pushNotifications$/},()=>({path:'push',namespace:'menu'}));b.onLoad({filter:/.*/,namespace:'menu'},()=>({contents:'export const readPushState=window.push.read;export const enablePushNotifications=window.push.enable;export const disablePushNotifications=window.push.disable;'}))}}]})
  const dom = new JSDOM('<div id="root"></div>',{url:'https://app.veraspa.vn',runScripts:'dangerously',pretendToBeVisual:true})
  let enabled = false, enabledCount = 0, disabledCount = 0
  const state = () => ({ supported:true, subscribed:enabled, permission:'granted' })
  dom.window.push = { read:async()=>state(),enable:async()=>{enabledCount++;enabled=true;return state()},disable:async()=>{disabledCount++;enabled=false;return state()} }
  try {
    dom.window.eval(rendered.outputFiles[0].text);dom.window.mount()
    await new Promise(resolve=>setTimeout(resolve,70))
    const button = dom.window.document.querySelector('[role=switch]')
    assert.equal(button.getAttribute('aria-checked'),'false')
    assert.match(button.getAttribute('aria-label'),/thiết bị này/)
    assert.equal(dom.window.document.querySelector('.device-push-menu > p'),null)
    assert.doesNotMatch(dom.window.document.body.textContent,/Tắt ở đây vẫn nhận/)
    button.click();await new Promise(resolve=>setTimeout(resolve,30))
    assert.equal(button.getAttribute('aria-checked'),'true');assert.equal(enabledCount,1)
    button.click();await new Promise(resolve=>setTimeout(resolve,30))
    assert.equal(button.getAttribute('aria-checked'),'false');assert.equal(disabledCount,1)
    dom.window.dispatchEvent(new dom.window.CustomEvent('vera-device-push-changed',{detail:{...state(),subscribed:true}}))
    await new Promise(resolve=>setTimeout(resolve,30))
    assert.equal(button.getAttribute('aria-checked'),'true')
  } finally { dom.window.close() }
})

test('opening signed out clears an earlier device owner even in a fresh page', async t => {
  const { w, calls, cache } = await device(t)
  await w.push.enablePushNotifications()
  w.eval(code)
  await w.push.setPushAccount('')
  assert.equal(cache.get('/__vera_push_device__').enabled, false)
  assert.equal(cache.get('/__vera_push_device__').owner, '')
  assert.equal(calls.removed, 1)
  assert.equal((await w.push.readPushState()).subscribed, false)
})
