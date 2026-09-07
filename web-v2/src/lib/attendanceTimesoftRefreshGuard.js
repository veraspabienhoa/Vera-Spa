import { getCurrentSession } from './supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const CHECK_PATH = '/v2/attendance/break-alerts/check'
const SNAPSHOT_PATH = '/v2/snapshot'
const MIN_CLIENT_REFRESH_MS = 12_000

let installed = false
let refreshPromise = null
let lastRefreshAt = 0
let lastResult = null

const dateText = (value = new Date()) => {
  const date = value instanceof Date ? value : new Date(value)
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}-${String(date.getDate()).padStart(2, '0')}`
}

function isTodayRange(url) {
  try {
    const parsed = new URL(url, window.location.origin)
    if (parsed.pathname !== SNAPSHOT_PATH) return false
    const start = parsed.searchParams.get('start') || ''
    const end = parsed.searchParams.get('end') || ''
    const today = dateText()
    return Boolean(start && end && start <= today && today <= end)
  } catch {
    return false
  }
}

function refreshError(payload) {
  const live = payload?.timesoft_live_refresh
  if (!live || live.ok !== false) return ''
  const raw = String(live.error || 'Không thể đồng bộ TimeSoft.').trim()
  if (live.error_code === 'TIMESOFT_AUTH_REJECTED') {
    return `Không thể lấy dữ liệu chấm công từ TimeSoft: tài khoản/mật khẩu TimeSoft trên máy chủ VERA đang bị TimeSoft từ chối. ${raw}`
  }
  return `Không thể lấy dữ liệu chấm công mới từ TimeSoft. ${raw}`
}

async function forceFreshAttendance(originalFetch) {
  const now = Date.now()
  if (lastResult && now - lastRefreshAt < MIN_CLIENT_REFRESH_MS) {
    const message = refreshError(lastResult)
    if (message) throw new Error(message)
    return lastResult
  }
  if (refreshPromise) return refreshPromise

  refreshPromise = (async () => {
    const session = await getCurrentSession()
    const headers = new Headers({ Accept: 'application/json' })
    if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
    const response = await originalFetch(`${API_BASE}${CHECK_PATH}`, {
      method: 'POST',
      headers,
      cache: 'no-store',
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) {
      throw new Error(payload.detail || payload.message || `Không kiểm tra được nguồn TimeSoft (HTTP ${response.status}).`)
    }
    lastRefreshAt = Date.now()
    lastResult = payload
    const message = refreshError(payload)
    if (message) throw new Error(message)
    return payload
  })().finally(() => {
    refreshPromise = null
  })
  return refreshPromise
}

export function startAttendanceTimesoftRefreshGuard() {
  if (installed || !API_BASE || typeof window === 'undefined' || typeof window.fetch !== 'function') return
  installed = true
  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input, init) => {
    const requestUrl = typeof input === 'string' || input instanceof URL ? String(input) : String(input?.url || '')
    if (isTodayRange(requestUrl)) {
      await forceFreshAttendance(originalFetch)
    }
    return originalFetch(input, init)
  }
}
