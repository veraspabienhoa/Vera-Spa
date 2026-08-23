import { getCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
export const isApiConfigured = Boolean(apiBase)
export const demoMode = import.meta.env.VITE_VERA_DEMO_MODE === '1'

async function request(path, options = {}) {
  if (!apiBase) throw new Error('VITE_VERA_API_BASE_URL chưa được cấu hình.')

  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)

  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  }
  return payload
}

export const veraApi = {
  health: () => request('/v2/health'),
  me: () => request('/v2/me'),
  leaveSummary: (date) => request(`/v2/leave/summary?date=${encodeURIComponent(date)}`),
  leaveRecords: (date) => request(`/v2/leave/records?date=${encodeURIComponent(date)}`),
  leaveReasons: () => request('/v2/leave/reasons'),
  createLeave: (body) => request('/v2/leave/records', { method: 'POST', body: JSON.stringify(body) }),
}
