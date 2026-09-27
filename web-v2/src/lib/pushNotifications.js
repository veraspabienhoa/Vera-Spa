import { veraApi } from './api'

const isIos = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent) || (window.navigator.platform === 'MacIntel' && window.navigator.maxTouchPoints > 1)
const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true

const decodeVapidKey = (value) => {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)))
}

const vapidKeyMatches = (subscription, publicKey) => {
  const current = subscription?.options?.applicationServerKey
  if (!current) return false
  const actual = new Uint8Array(current)
  const expected = decodeVapidKey(publicKey)
  if (actual.length !== expected.length) return false
  return actual.every((value, index) => value === expected[index])
}

export const getPushSupport = () => {
  if ('serviceWorker' in navigator && isIos() && !isStandalone()) {
    return {
      supported: false,
      needsHomeScreen: true,
      reason: 'Trên iPhone/iPad, hãy Thêm vào Màn hình chính rồi mở VERA SPA từ biểu tượng mới.',
    }
  }
  if (!('serviceWorker' in navigator) || !('PushManager' in window) || !('Notification' in window)) {
    return { supported: false, reason: 'Trình duyệt này chưa hỗ trợ thông báo Web Push.' }
  }
  return { supported: true, permission: Notification.permission }
}

export const registerVeraServiceWorker = async () => {
  const support = getPushSupport()
  if (!support.supported && !support.needsHomeScreen) return null
  return navigator.serviceWorker.register(`${import.meta.env.BASE_URL}sw.js`, {
    scope: import.meta.env.BASE_URL,
    updateViaCache: 'none',
  })
}

const PREFERENCE = 'vera:device-push:preference'
const OWNER = 'vera:device-push:owner'
const CONTROL_CACHE = 'vera-push-device-v1'
const CONTROL_PATH = '/__vera_push_device__'
let account = null, generation = 0, queue = Promise.resolve(), controlQueue = Promise.resolve(), syncing = null
const readLocal = key => { try { return localStorage.getItem(key) } catch { return null } }
const saveLocal = (key, value) => { localStorage.setItem(key, value) }
export const devicePushEnabled = () => readLocal(PREFERENCE) !== 'off'
const enqueue = operation => {
  const result = queue.catch(() => {}).then(operation)
  queue = result.catch(() => {})
  return result
}
const writeControl = (enabled, owner = account) => {
  const value = { enabled, owner }
  controlQueue = controlQueue.catch(() => {}).then(async () => {
    const cache = await caches.open(CONTROL_CACHE)
    await cache.put(CONTROL_PATH, new Response(JSON.stringify(value), { headers: { 'Content-Type': 'application/json' } }))
  })
  return controlQueue
}
const notify = async () => {
  const state = await readPushState()
  window.dispatchEvent(new CustomEvent('vera-device-push-changed', { detail: state }))
  return state
}
const removeSubscription = async registration => {
  const subscription = await registration?.pushManager.getSubscription()
  if (!subscription) return
  // Browser removal still runs when the API is offline or the account signed out.
  const results = await Promise.allSettled([
    subscription.unsubscribe(), veraApi.unregisterPushSubscription(subscription.endpoint),
  ])
  if (results.every(result => result.status === 'rejected')) throw new Error('Chưa hủy được đăng ký thiết bị. Hệ thống sẽ thử lại khi có kết nối.')
}

export const setPushAccount = id => {
  const next = String(id || '')
  if (account === next) return Promise.resolve()
  account = next; generation += 1; syncing = null
  // Stop display immediately; only a successful registration can reopen it.
  const blocked = writeControl(false, next).catch(() => {})
  return enqueue(async () => {
    await blocked
    if (!getPushSupport().supported) return
    if (!next || readLocal(OWNER) !== next) {
      const registration = await registerVeraServiceWorker()
      const visible = await registration.getNotifications()
      visible.forEach(notification => notification.close())
      await removeSubscription(registration).catch(() => {})
      saveLocal(OWNER, '')
    }
  })
}

export const readPushState = async () => {
  const support = getPushSupport()
  const enabled = devicePushEnabled()
  if (!support.supported) return { ...support, enabled, subscribed: false }
  const registration = await registerVeraServiceWorker()
  const subscription = await registration.pushManager.getSubscription()
  return { ...support, enabled, permission: Notification.permission,
    subscribed: enabled && Notification.permission === 'granted' && Boolean(subscription) && Boolean(account) && readLocal(OWNER) === account }
}

export const ensureGrantedPushSubscription = () => {
  if (syncing) return syncing
  const ticket = generation, owner = account
  const current = () => ticket === generation && owner === account && Boolean(owner) && devicePushEnabled()
  const job = enqueue(async () => {
    const support = getPushSupport()
    if (!support.supported || !current() || Notification.permission !== 'granted') {
      if (support.supported && !devicePushEnabled()) {
        await writeControl(false)
        await removeSubscription(await registerVeraServiceWorker()).catch(() => {})
      }
      return readPushState()
    }
    const config = await veraApi.pushConfig()
    if (!current()) return readPushState()
    if (!config.enabled || !config.public_key) {
      await writeControl(false)
      return { ...support, enabled: true, permission: Notification.permission, subscribed: false, serverEnabled: false,
        reason: 'Máy chủ chưa cấu hình thông báo màn hình khóa.' }
    }
    const registration = await registerVeraServiceWorker()
    if (!current()) return readPushState()
    let subscription = await registration.pushManager.getSubscription()
    if (subscription && (!vapidKeyMatches(subscription, config.public_key) || readLocal(OWNER) !== owner)) {
      await removeSubscription(registration)
      subscription = null
    }
    if (!current()) return readPushState()
    if (!subscription) subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true, applicationServerKey: decodeVapidKey(config.public_key),
    })
    if (!current()) { await removeSubscription(registration).catch(() => {}); return readPushState() }
    await veraApi.registerPushSubscription(subscription.toJSON())
    if (!current()) { await removeSubscription(registration).catch(() => {}); return readPushState() }
    saveLocal(OWNER, owner)
    await writeControl(true, owner)
    return { ...support, enabled: true, permission: Notification.permission, subscribed: true, serverEnabled: true }
  })
  const result = job.then(async state => {
    if (ticket !== generation) state = await readPushState()
    window.dispatchEvent(new CustomEvent('vera-device-push-changed', { detail: state }))
    return state
  }).finally(() => { if (syncing === result) syncing = null })
  syncing = result
  return result
}

export const syncExistingPushSubscription = () => ensureGrantedPushSubscription()

export const enablePushNotifications = async () => {
  const support = getPushSupport()
  if (!support.supported) throw new Error(support.reason)
  if (!account) throw new Error('Hãy đăng nhập trước khi bật thông báo.')
  const ticket = generation
  // Keep the permission request in the actual tap handler (required on iPhone).
  const permission = await Notification.requestPermission()
  if (ticket !== generation) return readPushState()
  if (permission !== 'granted') throw new Error(permission === 'denied'
    ? 'Quyền thông báo đang bị chặn. Hãy bật lại trong Cài đặt trình duyệt/điện thoại.'
    : 'Bạn chưa cho phép nhận thông báo.')
  saveLocal(PREFERENCE, 'on')
  syncing = null
  return ensureGrantedPushSubscription()
}

export const disablePushNotifications = () => {
  saveLocal(PREFERENCE, 'off')
  generation += 1; syncing = null
  const blocked = writeControl(false)
  return enqueue(async () => {
    await blocked
    if (getPushSupport().supported) {
      const registration = await registerVeraServiceWorker()
      const visible = await registration.getNotifications()
      visible.forEach(notification => notification.close())
      await removeSubscription(registration)
    }
    return notify()
  })
}

if (typeof window !== 'undefined') window.addEventListener('storage', event => {
  if (event.key === PREFERENCE || event.key === OWNER) {
    generation += 1; syncing = null
    if (!devicePushEnabled()) void writeControl(false).catch(() => {})
    void notify().catch(() => {})
  }
})
