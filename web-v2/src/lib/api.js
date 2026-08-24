import { getCurrentSession, isSupabaseConfigured, supabase } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
export const isApiConfigured = Boolean(apiBase)
export const isReadConfigured = Boolean(apiBase || isSupabaseConfigured)

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

async function download(path, fallbackName) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers()
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const filename = encoded ? decodeURIComponent(encoded) : fallbackName
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  URL.revokeObjectURL(url)
}

async function upload(path, file) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers()
  headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { method: 'POST', headers, body: file })
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

function datesBetween(start, end) {
  const dates = []
  const cursor = new Date(`${start}T00:00:00`)
  const finish = new Date(`${end}T00:00:00`)
  while (cursor <= finish && dates.length < 366) {
    const year = cursor.getFullYear()
    const month = `${cursor.getMonth() + 1}`.padStart(2, '0')
    const day = `${cursor.getDate()}`.padStart(2, '0')
    dates.push(`${year}-${month}-${day}`)
    cursor.setDate(cursor.getDate() + 1)
  }
  return dates
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
  leaveRecords: async (start, end = start) => {
    if (isApiConfigured) return request(`/v2/leave/records?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`)
    const batches = await Promise.all(datesBetween(start, end).map(async (date) => {
      const rows = await rpc('vera_v2_leave_records', { p_date: date })
      return (Array.isArray(rows) ? rows : []).map((row) => ({ ...row, leave_date: row.leave_date || date }))
    }))
    return { records: batches.flat() }
  },
  leaveReasons: async (date) => {
    if (isApiConfigured) return request(`/v2/leave/reasons?date=${encodeURIComponent(date)}`)
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
  staff: () => request('/v2/staff'),
  createStaff: (body) => request('/v2/staff', { method: 'POST', body: JSON.stringify(body) }),
  updateStaff: (username, body) => request(`/v2/staff/${encodeURIComponent(username)}`, {
    method: 'PATCH',
    body: JSON.stringify(body),
  }),
  deleteStaff: (usernames) => request('/v2/staff', {
    method: 'DELETE',
    body: JSON.stringify({ usernames }),
  }),
  exportStaffExcel: (search = '', role = '', status = '', shift = '') => {
    const params = new URLSearchParams()
    if (search.trim()) params.set('search', search.trim())
    if (role) params.set('role', role)
    if (status) params.set('status', status)
    if (shift) params.set('shift', shift)
    const query = params.toString()
    return download(`/v2/staff/export.xlsx${query ? `?${query}` : ''}`, 'VeraSpa_DanhSachNhanSu.xlsx')
  },
  importStaffExcel: (file) => upload('/v2/staff/import.xlsx', file),
  rules: () => request('/v2/rules'),
  saveRules: (body) => request('/v2/rules', { method: 'PUT', body: JSON.stringify(body) }),
  saveDailyQuota: (body) => request('/v2/rules/daily-quota', { method: 'PUT', body: JSON.stringify(body) }),
  exportRulesExcel: () => download('/v2/rules/export.xlsx', 'NoiQuy_VeraSpa.xlsx'),
  importRulesExcel: (file) => upload('/v2/rules/import.xlsx', file),
  longLeaveOverview: () => request('/v2/long-leave/overview'),
  createLongLeaveRequest: (body) => request('/v2/long-leave/requests', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  profile: () => request('/v2/profile'),
  profileReferenceData: (provinceCode = '') => request(`/v2/profile/reference-data${provinceCode === '' ? '' : `?province_code=${encodeURIComponent(provinceCode)}`}`),
  updateProfile: (body) => request('/v2/profile', { method: 'PATCH', body: JSON.stringify(body) }),
  permissions: () => request('/v2/permissions'),
  savePermissions: (scope, target, body) => request(`/v2/permissions/${encodeURIComponent(scope)}/${encodeURIComponent(target)}`, {
    method: 'PUT', body: JSON.stringify(body),
  }),
  payrollHistory: (batch = '', search = '') => {
    const params = new URLSearchParams()
    if (batch) params.set('batch', batch)
    if (search.trim()) params.set('search', search.trim())
    return request(`/v2/payroll/history?${params}`)
  },
  exportPayrollExcel: (batch = '', search = '') => {
    const params = new URLSearchParams()
    if (batch) params.set('batch', batch)
    if (search.trim()) params.set('search', search.trim())
    return download(`/v2/payroll/history/export.xlsx?${params}`, 'VERA_BangLuong.xlsx')
  },
  snapshot: (start, end) => request(`/v2/snapshot?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  exportSnapshotExcel: (start, end) => download(`/v2/snapshot/export.xlsx?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`, 'VERA_Snapshot_ChamCong.xlsx'),
  adminChanges: (days = 7) => request(`/v2/admin/changes?days=${encodeURIComponent(days)}`),
  storagePreview: (start, end) => request(`/v2/storage/preview?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  exportStorageExcel: (start, end, dataset = 'all') => download(`/v2/storage/export.xlsx?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&dataset=${encodeURIComponent(dataset)}`, 'VERA_LuuTru.xlsx'),
  deleteStorageData: (body) => request('/v2/storage', { method: 'DELETE', body: JSON.stringify(body) }),
  createLeave: (body) => request('/v2/leave/records', { method: 'POST', body: JSON.stringify(body) }),
  updateLeave: (recordUid, body) => request(`/v2/leave/records/${encodeURIComponent(recordUid)}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deleteLeaves: (recordUids) => request('/v2/leave/records', { method: 'DELETE', body: JSON.stringify({ record_uids: recordUids }) }),
  watchDates: () => request('/v2/leave/watch-dates'),
  setWatchDate: (watchedDate, watching) => request('/v2/leave/watch-dates', {
    method: 'POST',
    body: JSON.stringify({ watched_date: watchedDate, watching }),
  }),
  acknowledgeWatchDates: (watchedDates) => request('/v2/leave/watch-dates/acknowledge', {
    method: 'POST',
    body: JSON.stringify({ watched_dates: watchedDates }),
  }),
  pushConfig: () => request('/v2/push/config'),
  registerPushSubscription: (subscription) => request('/v2/push/subscriptions', {
    method: 'POST',
    body: JSON.stringify({ subscription }),
  }),
  unregisterPushSubscription: (endpoint) => request('/v2/push/subscriptions', {
    method: 'DELETE',
    body: JSON.stringify({ endpoint }),
  }),
  exportLeaveExcel: (start, end, employee = '') => {
    const params = new URLSearchParams({ start, end })
    if (employee.trim()) params.set('employee', employee.trim())
    return download(`/v2/leave/export.xlsx?${params}`, `vera-lich-nghi-${start}-${end}.xlsx`)
  },
}
