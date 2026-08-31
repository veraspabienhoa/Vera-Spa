import { veraApi } from './api'

const isIos = () => /iphone|ipad|ipod/i.test(window.navigator.userAgent)
const isStandalone = () => window.matchMedia('(display-mode: standalone)').matches || window.navigator.standalone === true

const decodeVapidKey = (value) => {
  const padding = '='.repeat((4 - (value.length % 4)) % 4)
  const base64 = (value + padding).replace(/-/g, '+').replace(/_/g, '/')
  const raw = window.atob(base64)
  return Uint8Array.from([...raw].map((character) => character.charCodeAt(0)))
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

export const readPushState = async () => {
  const support = getPushSupport()
  if (!support.supported) return { ...support, subscribed: false }
  const registration = await registerVeraServiceWorker()
  const subscription = await registration.pushManager.getSubscription()
  return { ...support, permission: Notification.permission, subscribed: Boolean(subscription) }
}

export const syncExistingPushSubscription = async () => {
  const support = getPushSupport()
  if (!support.supported || Notification.permission !== 'granted') return readPushState()
  const registration = await registerVeraServiceWorker()
  const subscription = await registration.pushManager.getSubscription()
  if (subscription) await veraApi.registerPushSubscription(subscription.toJSON())
  return { ...support, permission: Notification.permission, subscribed: Boolean(subscription) }
}

// Used after every authenticated login/focus. If the user has already granted
// notification permission, silently create/recover the PushSubscription and
// register it against the current VERA account. No permission prompt is shown,
// so this also works safely for an installed iPhone/iPad Home Screen PWA.
export const ensureGrantedPushSubscription = async () => {
  const support = getPushSupport()
  if (!support.supported || Notification.permission !== 'granted') {
    return { ...support, permission: 'Notification' in window ? Notification.permission : 'unsupported', subscribed: false }
  }

  const config = await veraApi.pushConfig()
  if (!config.enabled || !config.public_key) {
    return { ...support, permission: Notification.permission, subscribed: false, serverEnabled: false }
  }

  const registration = await registerVeraServiceWorker()
  if (!registration) return { ...support, permission: Notification.permission, subscribed: false }

  let subscription = await registration.pushManager.getSubscription()
  if (!subscription) {
    subscription = await registration.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: decodeVapidKey(config.public_key),
    })
  }
  await veraApi.registerPushSubscription(subscription.toJSON())
  return { ...support, permission: Notification.permission, subscribed: true, serverEnabled: true }
}

export const enablePushNotifications = async () => {
  const support = getPushSupport()
  if (!support.supported) throw new Error(support.reason)
  const permission = await Notification.requestPermission()
  if (permission !== 'granted') {
    throw new Error(permission === 'denied'
      ? 'Quyền thông báo đang bị chặn. Hãy bật lại trong Cài đặt trình duyệt/điện thoại.'
      : 'Bạn chưa cho phép nhận thông báo.')
  }
  return ensureGrantedPushSubscription()
}

export const disablePushNotifications = async () => {
  const support = getPushSupport()
  if (!support.supported) return { ...support, subscribed: false }
  const registration = await registerVeraServiceWorker()
  const subscription = await registration.pushManager.getSubscription()
  if (subscription) {
    await veraApi.unregisterPushSubscription(subscription.endpoint)
    await subscription.unsubscribe()
  }
  return { ...support, permission: Notification.permission, subscribed: false }
}
