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

  // Creation belongs to the durable event worker. The foreground only closes
  // resolved alerts, avoiding duplicate or device-opt-out-bypassing notifications.
}
