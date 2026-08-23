import { getCurrentSession, isSupabaseConfigured, supabase } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
export const isApiConfigured = Boolean(apiBase)
export const isReadConfigured = Boolean(apiBase || isSupabaseConfigured)
export const demoMode = import.meta.env.VITE_VERA_DEMO_MODE === '1'

async function request(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')

  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)

  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function rpc(name, args = {}) {
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')
  const { data, error } = await supabase.rpc(name, args)
  if (error) throw error
  return data
}

export const veraApi = {
  health: () => request('/v2/health'),
  me: async () => {
    if (isApiConfigured) return request('/v2/me')
    const rows = await rpc('vera_v2_me')
    return Array.isArray(rows) ? rows[0] || null : rows
  },
  leaveSummary: async (date) => {
    if (isApiConfigured) return request(`/v2/leave/summary?date=${encodeURIComponent(date)}`)
    const rows = await rpc('vera_v2_leave_summary', { p_date: date })
    const row = Array.isArray(rows) ? rows[0] : rows
    return row || { working: 0, leave: 0, paid: 0, unpaid: 0 }
  },
  leaveDailyStats: async (start, end) => {
    if (isApiConfigured) {
      return request(`/v2/leave/daily-stats?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`)
    }
    const rows = await rpc('vera_v2_leave_daily_stats', { p_start: start, p_end: end })
    return {
      days: Array.isArray(rows) ? rows.map((row) => ({ ...row, date: row.date || row.day })) : [],
    }
  },
  leaveRecords: async (date) => {
    if (isApiConfigured) return request(`/v2/leave/records?date=${encodeURIComponent(date)}`)
    const rows = await rpc('vera_v2_leave_records', { p_date: date })
    return { records: Array.isArray(rows) ? rows : [] }
  },
  leaveReasons: async () => {
    if (isApiConfigured) return request('/v2/leave/reasons')
    const rows = await rpc('vera_v2_leave_reasons')
    return {
      reasons: (rows || []).map((row) => ({
        name: row.reason,
        days: null,
        penalty: null,
        requires_manual_penalty: false,
      })).filter((row) => row.name),
    }
  },
  employees: async () => {
    if (isApiConfigured) return request('/v2/employees')
    const rows = await rpc('vera_v2_employees')
    return { employees: Array.isArray(rows) ? rows : [] }
  },
  createLeave: (body) => request('/v2/leave/records', { method: 'POST', body: JSON.stringify(body) }),
}
