const APP_URL = '/Vera-Spa/'
const ICON_URL = '/Vera-Spa/icons/vera-icon-192.png'
const BADGE_URL = '/Vera-Spa/icons/vera-icon-192.png'

self.addEventListener('install', () => self.skipWaiting())
self.addEventListener('activate', (event) => event.waitUntil(self.clients.claim()))

self.addEventListener('push', (event) => {
  let payload = {}
  try {
    payload = event.data ? event.data.json() : {}
  } catch {
    payload = { body: event.data?.text() || '' }
  }

  const isAdminChange = payload.kind === 'admin-system-change'
  const title = payload.title || 'VERA SPA · Lịch nghỉ thay đổi'
  const options = {
    body: payload.body || 'Một ngày bạn quan tâm vừa thay đổi số lịch nghỉ CÓ phép.',
    icon: payload.icon || ICON_URL,
    badge: payload.badge || BADGE_URL,
    tag: payload.tag || 'vera-spa-leave-watch',
    renotify: true,
    requireInteraction: true,
    silent: false,
    vibrate: [220, 100, 220, 100, 360],
    timestamp: Number(payload.timestamp || Date.now()),
    data: {
      url: payload.url || APP_URL,
      watchedDate: payload.watched_date || '',
      kind: payload.kind || '',
      changeId: payload.change_id || null,
    },
  }

  if (isAdminChange) {
    // Admin system-change notifications must be easy to dismiss by native
    // swipe while leave-watch alerts retain their existing sticky behavior.
    options.requireInteraction = false
    options.actions = [
      { action: 'open', title: 'Xem chi tiết' },
      { action: 'dismiss', title: 'Xóa' },
    ]
  }

  event.waitUntil(self.registration.showNotification(title, options))
})

self.addEventListener('notificationclick', (event) => {
  const action = event.action || 'open'
  event.notification.close()
  if (action === 'dismiss') return

  const targetUrl = new URL(event.notification.data?.url || APP_URL, self.location.origin).href
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if (client.url.startsWith(self.location.origin) && 'focus' in client) {
        if ('navigate' in client) await client.navigate(targetUrl)
        return client.focus()
      }
    }
    return self.clients.openWindow ? self.clients.openWindow(targetUrl) : undefined
  })())
})
