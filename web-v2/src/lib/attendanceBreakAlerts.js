import { getCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function authHeaders() {
  const session = await getCurrentSession()
  const headers = new Headers({ 'Content-Type': 'application/json' })
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  return headers
}

export async function checkAttendanceBreakAlerts() {
  if (!apiBase) return { alerts: [], alert_count: 0 }
  const response = await fetch(`${apiBase}/v2/attendance/break-alerts/check`, {
    method: 'POST',
    headers: await authHeaders(),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export async function getAttendanceBreakAlertControl() {
  if (!apiBase) return { disabled: false }
  const response = await fetch(`${apiBase}/v2/attendance/break-alerts/control`, {
    headers: await authHeaders(),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export async function setAttendanceBreakAlertControl(disabled) {
  if (!apiBase) return { disabled: Boolean(disabled) }
  const response = await fetch(`${apiBase}/v2/attendance/break-alerts/control`, {
    method: 'PUT',
    headers: await authHeaders(),
    body: JSON.stringify({ disabled: Boolean(disabled) }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export async function syncPersistentBreakNotifications(alerts = []) {
  if (!('serviceWorker' in navigator) || !('Notification' in window) || Notification.permission !== 'granted') return
  const registration = await navigator.serviceWorker.ready.catch(() => null)
  if (!registration) return

  const activeTags = new Set((alerts || []).map((item) => item.tag).filter(Boolean))
  const existing = await registration.getNotifications().catch(() => [])
  for (const notification of existing) {
    if (String(notification.tag || '').startsWith('vera-break-') && !activeTags.has(notification.tag)) notification.close()
  }

  for (const item of alerts || []) {
    if (!item.tag) continue
    const sameTag = await registration.getNotifications({ tag: item.tag }).catch(() => [])
    if (sameTag.length) continue
    const overdue = item.level === 'overdue'
    const title = overdue
      ? `VERA SPA · ${item.employee} VÀO LẠI TRỄ`
      : 'VERA SPA · Sắp hết giờ nghỉ giữa ca'
    const remainingMinutes = Math.max(1, Math.ceil(Math.max(0, Number(item.remaining_seconds || 0)) / 60))
    const lateMinutes = Math.max(1, Math.ceil(Math.max(0, Number(item.late_seconds || 0)) / 60))
    const body = overdue
      ? `${item.employee}: nghỉ từ ${item.break_out}, phải vào lại ${item.deadline}, hiện đã trễ ${lateMinutes} phút.`
      : `${item.employee}: còn ${remainingMinutes} phút. Nghỉ từ ${item.break_out}, phải FaceID vào lại lúc ${item.deadline}.`
    await registration.showNotification(title, {
      body,
      icon: `${import.meta.env.BASE_URL}icons/vera-icon-192.png`,
      badge: `${import.meta.env.BASE_URL}icons/vera-icon-192.png`,
      tag: item.tag,
      renotify: true,
      requireInteraction: overdue,
      silent: false,
      vibrate: overdue ? [260, 120, 260, 120, 420] : [180, 90, 240],
      data: { url: import.meta.env.BASE_URL, kind: overdue ? 'attendance-break-overdue' : 'attendance-break-reminder' },
    })
  }
}
