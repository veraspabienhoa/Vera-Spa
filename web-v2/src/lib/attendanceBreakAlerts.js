import { getCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const MIN_CHECK_INTERVAL_MS = 12_000
let breakAlertCheckPromise = null
let breakAlertLastCheckedAt = 0
let breakAlertLastPayload = { alerts: [], alert_count: 0, degraded: false }

async function authHeaders() {
  const session = await getCurrentSession()
  if (!session?.access_token) return null
  const headers = new Headers({ 'Content-Type': 'application/json' })
  headers.set('Authorization', `Bearer ${session.access_token}`)
  return headers
}

function degradedBreakAlertPayload(status = 0, payload = {}) {
  return {
    alerts: [],
    alert_count: 0,
    degraded: true,
    status,
    message: payload.detail || payload.message || 'Tạm thời không kiểm tra được cảnh báo nghỉ giữa ca.',
  }
}

export async function checkAttendanceBreakAlerts() {
  if (!apiBase) return { alerts: [], alert_count: 0 }
  const now = Date.now()
  if (breakAlertCheckPromise) return breakAlertCheckPromise
  if (now - breakAlertLastCheckedAt < MIN_CHECK_INTERVAL_MS) return breakAlertLastPayload

  breakAlertCheckPromise = (async () => {
    try {
      const headers = await authHeaders()
      if (!headers) return degradedBreakAlertPayload(401, { message: 'Chưa có phiên đăng nhập hợp lệ.' })
      const response = await fetch(`${apiBase}/v2/attendance/break-alerts/check`, {
        method: 'POST',
        headers,
      })
      const payload = await response.json().catch(() => ({}))
      if (!response.ok) {
        if ([401, 500, 502, 503, 504].includes(response.status)) return degradedBreakAlertPayload(response.status, payload)
        throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
      }
      breakAlertLastPayload = payload
      return payload
    } catch (error) {
      breakAlertLastPayload = degradedBreakAlertPayload(0, { message: error?.message })
      return breakAlertLastPayload
    } finally {
      breakAlertLastCheckedAt = Date.now()
      breakAlertCheckPromise = null
    }
  })()
  return breakAlertCheckPromise
}

export async function getAttendanceBreakAlertControl() {
  if (!apiBase) return { disabled: false }
  const headers = await authHeaders()
  if (!headers) return { disabled: false }
  const response = await fetch(`${apiBase}/v2/attendance/break-alerts/control`, {
    headers,
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export async function setAttendanceBreakAlertControl(disabled) {
  if (!apiBase) return { disabled: Boolean(disabled) }
  const headers = await authHeaders()
  if (!headers) return { disabled: Boolean(disabled) }
  const response = await fetch(`${apiBase}/v2/attendance/break-alerts/control`, {
    method: 'PUT',
    headers,
    body: JSON.stringify({ disabled: Boolean(disabled) }),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export async function deleteAttendanceBreakAlertForAll(key, tag) {
  if (!apiBase) return { globally_deleted: true, key, tag }
  const headers = await authHeaders()
  if (!headers) return { globally_deleted: false, key, tag }
  const params = new URLSearchParams({ key: String(key || ''), tag: String(tag || '') })
  const response = await fetch(`${apiBase}/v2/attendance/break-alerts/item?${params.toString()}`, {
    method: 'DELETE',
    headers,
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
    if (/^vera-(break|missing-checkin)-/.test(String(notification.tag || '')) && !activeTags.has(notification.tag)) notification.close()
  }

  for (const item of alerts || []) {
    if (!item.tag) continue
    const sameTag = await registration.getNotifications({ tag: item.tag }).catch(() => [])
    if (sameTag.length) continue
    const overdue = item.level === 'overdue'
    const title = item.kind === 'missing-scheduled-checkin' ? 'VERA SPA · CHƯA CHECK-IN' : overdue
      ? `VERA SPA · ${item.employee} VÀO LẠI TRỄ`
      : 'VERA SPA · Sắp hết giờ nghỉ giữa ca'
    const remainingMinutes = Math.max(1, Math.ceil(Math.max(0, Number(item.remaining_seconds || 0)) / 60))
    const lateMinutes = Math.max(1, Math.ceil(Math.max(0, Number(item.late_seconds || 0)) / 60))
    const body = item.kind === 'missing-scheduled-checkin' ? item.body : overdue
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