import { notifyLeaveChange } from './leaveRefresh'
import { getCurrentSession, isSupabaseConfigured, refreshCurrentSession, supabase } from './supabase'
import { apiErrorMessage } from './apiError'
import { summarizeLeaveRecordDays } from './leaveStats'
import { apiBase } from './apiConfig'
import { authJsonRequest } from './authTransport'

export const isApiConfigured = Boolean(apiBase)
export const isReadConfigured = Boolean(apiBase || isSupabaseConfigured)

async function request(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')

  let session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)

  const method = String(options.method || 'GET').toUpperCase()
  // Cloud Run can need a few seconds to wake or switch revisions. Three GET
  // attempts prevent a transient rollout/cold-start from becoming a false
  // "Failed to fetch" screen while keeping writes single-shot.
  const attempts = path === '/v2/me' ? 1 : method === 'GET' || path === '/v2/payroll/history/sync-legacy'
    ? 3
    : path === '/v2/payroll/save' ? 2 : 1
  const send = async () => {
    let lastError
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        if (path === '/v2/me') return await authJsonRequest(`${apiBase}${path}`, { ...options, headers })
        const response = await fetch(`${apiBase}${path}`, { ...options, headers })
        return { response, payload: await response.json().catch(() => ({})) }
      } catch (error) {
        lastError = error
        if (attempt < attempts) await new Promise((resolve) => setTimeout(resolve, attempt * 1200))
      }
    }
    if (path === '/v2/me') throw lastError
    throw new Error(`Không kết nối được máy chủ VERA sau ${attempts} lần thử. Vui lòng bấm Làm mới. (${lastError?.message || 'Lỗi mạng'})`)
  }
  let { response, payload } = await send()
  if (response.status === 401 && session?.refresh_token) {
    // Keep refresh outside transport retries: its 503/timeout must propagate,
    // not be replaced by the original 401 and trigger a false logout in App.
    session = await refreshCurrentSession(session)
    if (session?.access_token) {
      headers.set('Authorization', `Bearer ${session.access_token}`)
      ;({ response, payload } = await send())
    }
  }
  if (!response.ok) {
    const error = new Error(apiErrorMessage(payload, response.status))
    error.status = response.status
    error.payload = payload
    throw error
  }
  return payload
}

async function binaryResponse(path, options = {}, failureMessage = 'Không tải được dữ liệu sau 2 lần thử') {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  let session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  let response
  let lastError
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      response = await fetch(`${apiBase}${path}`, { ...options, headers })
      break
    } catch (error) {
      lastError = error
      if (attempt === 1) await new Promise((resolve) => setTimeout(resolve, 800))
    }
  }
  if (!response) throw new Error(`${failureMessage}. (${lastError?.message || 'Lỗi mạng'})`)
  if (response.status === 401 && session?.refresh_token) {
    session = await refreshCurrentSession(session)
    if (session?.access_token) {
      headers.set('Authorization', `Bearer ${session.access_token}`)
      response = await fetch(`${apiBase}${path}`, { ...options, headers })
    }
  }
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    const error = new Error(apiErrorMessage(payload, response.status))
    error.status = response.status
    throw error
  }
  return response
}

async function download(path, fallbackName, options = {}) {
  const response = await binaryResponse(path, options, 'Không tải được file Excel sau 2 lần thử')
  const blob = await response.blob()
  const disposition = response.headers.get('Content-Disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  let filename = fallbackName
  if (encoded) {
    try {
      filename = decodeURIComponent(encoded.replace(/^"|"$/g, ''))
    } catch {
      filename = fallbackName
    }
  }
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
}

async function upload(path, file, params = null) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers()
  headers.set('Content-Type', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const query = params ? `?${new URLSearchParams(params)}` : ''
  let response
  let lastError
  for (let attempt = 1; attempt <= 2; attempt += 1) {
    try {
      response = await fetch(`${apiBase}${path}${query}`, { method: 'POST', headers, body: file })
      break
    } catch (error) {
      lastError = error
      if (attempt === 1) await new Promise((resolve) => setTimeout(resolve, 800))
    }
  }
  if (!response) throw new Error(`Không gửi được file Excel tới máy chủ VERA sau 2 lần thử. (${lastError?.message || 'Lỗi mạng'})`)
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(apiErrorMessage(payload, response.status))
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

function liveTourExportParams(kind, query = {}) {
  const params = new URLSearchParams({ kind })
  for (const key of ['columns', 'employee_ids']) {
    if (Array.isArray(query[key])) query[key].forEach((value) => params.append(key, String(value)))
  }
  for (const key of ['bill_no', 'employee', 'customer', 'service', 'report_kind', 'performance_timing', 'date_from', 'date_to', 'time_from', 'time_to', 'include_hidden', 'customer_id']) {
    const value = String(query?.[key] ?? '').trim()
    if (value) params.set(key, value)
  }
  return params
}

export const veraApi = {
  purchases: params => request(`/v2/purchases?${new URLSearchParams(params)}`),
  createPurchases: body => request('/v2/purchases', { method: 'POST', body: JSON.stringify(body) }),
  editPurchase: (id, body) => request(`/v2/purchases/${id}`, { method: 'PATCH', body: JSON.stringify(body) }),
  deletePurchase: (id, revision) => request(`/v2/purchases/${id}?revision=${revision}`, { method: 'DELETE' }),
  importPurchases: (file, mode) => upload('/v2/purchases/import', file, { mode, request_id: crypto.randomUUID() }),
  exportPurchases: params => download(`/v2/purchases/export.xlsx?${new URLSearchParams(params)}`, 'NhapMua.xlsx'),
  purchaseAudit: () => request('/v2/purchases/audit'),
  products: () => request('/v2/products'),
  saveProduct: (body) => request(body.id ? `/v2/products/${encodeURIComponent(body.id)}` : '/v2/products', { method:body.id ? 'PUT' : 'POST', body:JSON.stringify(body) }),
  uiLayoutHistory: () => request('/v2/ui-layout/history'),
  restoreUiLayout: (revision, body) => request(`/v2/ui-layout/restore/${revision}`, { method: 'POST', body: JSON.stringify(body) }),
  leaveQuotaCheck: (start, end) => request(`/v2/leave/quota-check?${new URLSearchParams({ start, end })}`),
  hr: () => request('/v2/hr'),
  saveHrDepartment: body => request('/v2/hr/departments', { method: 'PUT', body: JSON.stringify(body) }),
  deleteHrDepartment: (code, revision) => request(`/v2/hr/departments/${encodeURIComponent(code)}`, { method: 'DELETE', body: JSON.stringify({ revision }) }),
  assignHrDepartment: (username, department, revision) => request(`/v2/hr/employees/${encodeURIComponent(username)}/department`, { method: 'PUT', body: JSON.stringify({ department, revision }) }),
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
  leaveDailyStats: async (start, end, employee = '') => {
    if (isApiConfigured) {
      const params = new URLSearchParams({ start, end })
      if (employee.trim()) params.set('employee', employee.trim())
      return request(`/v2/leave/daily-stats?${params}`)
    }
    const rows = await rpc('vera_v2_leave_daily_stats', { p_start: start, p_end: end })
    return {
      days: Array.isArray(rows) ? rows.map((row) => ({ ...row, date: row.date || row.day })) : [],
    }
  },
  leaveListStats: async (start, end, employee = '') => {
    if (isApiConfigured) {
      const params = new URLSearchParams({ start, end })
      if (employee.trim()) params.set('employee', employee.trim())
      return request(`/v2/leave/list-stats?${params}`)
    }
    const batches = await Promise.all(datesBetween(start, end).map(async (date) => {
      const rows = await rpc('vera_v2_leave_records', { p_date: date })
      return (Array.isArray(rows) ? rows : []).map((row) => ({ ...row, leave_date: row.leave_date || date }))
    }))
    return { summary: summarizeLeaveRecordDays(batches.flat(), employee) }
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
  saveDepartmentRules: (department, body) => request(`/v2/rules/department/${encodeURIComponent(department)}`, { method: 'PUT', body: JSON.stringify(body) }),
  saveDailyQuota: (body) => request('/v2/rules/daily-quota', { method: 'PUT', body: JSON.stringify(body) }),
  saveLateThreshold: (body) => request('/v2/rules/late-threshold', { method: 'PUT', body: JSON.stringify(body) }),
  saveWeekendUnpaidNthPenalty: (body) => request('/v2/rules/weekend-unpaid-nth-penalty', { method: 'PUT', body: JSON.stringify(body) }),
  saveEmployeeSelfServicePolicy: (body) => request('/v2/rules/employee-self-service-policy', { method: 'PUT', body: JSON.stringify(body) }),
  saveLetanLeavePolicy: (body) => request('/v2/rules/letan-leave-policy', { method: 'PUT', body: JSON.stringify(body) }),
  exportRulesExcel: () => download('/v2/rules/export.xlsx', 'NoiQuy_VeraSpa.xlsx'),
  importRulesExcel: (file) => upload('/v2/rules/import.xlsx', file),
  longLeaveOverview: () => request('/v2/long-leave/overview'),
  createLongLeaveRequest: (body) => request('/v2/long-leave/requests', {
    method: 'POST',
    body: JSON.stringify(body),
  }),
  markLongLeaveReturned: (requestId, body) => request(`/v2/long-leave/admin/requests/${encodeURIComponent(requestId)}/return-to-work`, {
    method: 'POST', body: JSON.stringify(body),
  }),
  profile: () => request('/v2/profile'),
  profileReferenceData: (provinceCode = '') => request(`/v2/profile/reference-data${provinceCode === '' ? '' : `?province_code=${encodeURIComponent(provinceCode)}`}`),
  updateProfile: (body) => request('/v2/profile', { method: 'PATCH', body: JSON.stringify(body) }),
  renameSystemName: (username, systemName) => request(`/v2/staff/${encodeURIComponent(username)}/system-name`, {
    method: 'PATCH', body: JSON.stringify({ system_name: systemName }),
  }),
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
  syncLegacyPayroll: () => request('/v2/payroll/history/sync-legacy', { method: 'POST' }),
  exportPayrollExcel: (batch = '', search = '') => {
    const params = new URLSearchParams()
    if (batch) params.set('batch', batch)
    if (search.trim()) params.set('search', search.trim())
    return download(`/v2/payroll/history/export.xlsx?${params}`, 'VERA_BangLuong_BanCu.xlsx')
  },
  exportPayrollDraft: (body) => download('/v2/payroll/draft/export.xlsx', 'VERA_BangLuong_BanMoi.xlsx', {
    method: 'POST', body: JSON.stringify(body),
  }),
  payrollDraft: (month, periodNo, latestIfMissing = false) => request(`/v2/payroll/draft?${new URLSearchParams({
    month,
    period_no: periodNo,
    ...(latestIfMissing ? { latest_if_missing: 'true' } : {}),
  })}`),
  savePayrollDraft: (body) => request('/v2/payroll/draft', { method: 'PUT', body: JSON.stringify(body) }),
  deletePayrollDraft: (month, periodNo) => request(`/v2/payroll/draft?${new URLSearchParams({ month, period_no: periodNo })}`, { method: 'DELETE' }),
  importPayrollDraft: (file, month, periodNo) => upload('/v2/payroll/draft/import.xlsx', file, { month, period_no: periodNo }),
  payrollConfig: () => request('/v2/payroll/config'),
  savePayrollConfig: (body) => request('/v2/payroll/config', { method: 'PUT', body: JSON.stringify(body) }),
  payrollAccumulationRefunds: () => request('/v2/payroll/accumulation-refunds'),
  createPayrollAccumulationRefund: (body) => request('/v2/payroll/accumulation-refunds', { method: 'POST', body: JSON.stringify(body) }),
  deletePayrollAccumulationRefund: (id) => request(`/v2/payroll/accumulation-refunds/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  calculatePayroll: (file, month, periodNo) => upload('/v2/payroll/calculate', file, { month, period_no: periodNo }),
  calculatePayrollFromTips: (month, periodNo) => request(`/v2/payroll/calculate-from-tips?${new URLSearchParams({ month, period_no: periodNo })}`, { method: 'POST' }),
  savePayroll: (body) => request('/v2/payroll/save', { method: 'POST', body: JSON.stringify(body) }),
  emailPayroll: (body) => request('/v2/payroll/email', { method: 'POST', body: JSON.stringify(body) }),
  payrollObligations: () => request('/v2/payroll/obligations'),
  createPayrollObligation: (body) => request('/v2/payroll/obligations', { method: 'POST', body: JSON.stringify(body) }),
  deletePayrollObligation: (id) => request(`/v2/payroll/obligations/${encodeURIComponent(id)}`, { method: 'DELETE' }),
  snapshot: (start, end) => request(`/v2/snapshot?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  deviceRegistry: () => request('/v2/devices/registry'),
  saveDeviceRegistry: body => request('/v2/devices/registry', { method: 'PUT', body: JSON.stringify(body) }),
  checkinHistory: query => request(`/v2/devices/checkin-history?${new URLSearchParams(Object.entries(query).filter(([, value]) => value !== ''))}`),
  exportCheckinHistory: query => download(`/v2/devices/checkin-history/export.xlsx?${new URLSearchParams(Object.entries(query).filter(([, value]) => value !== ''))}`, 'VERA_LichSu_Checkin.xlsx'),
  attendanceSource: () => request('/v2/devices/attendance-source'),
  facegateMappings: () => request('/v2/devices/facegate-mappings'),
  facegateProfile: (id) => request(`/v2/devices/facegate-profiles/${encodeURIComponent(id)}`),
  saveFacegateMapping: (body) => request('/v2/devices/facegate-mappings', { method: 'POST', body: JSON.stringify(body) }),
  checkFacegateMapping: (registration_ref) => request('/v2/devices/facegate-mappings/check', { method: 'POST', body: JSON.stringify({ registration_ref }) }),
  facegateControlLog: (start, end) => request(`/v2/devices/control-log?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  facegateCaptureLog: (start, end) => request(`/v2/devices/capture-log?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  facegateCaptureImage: (imageRef) => {
    const params = new URLSearchParams({
      file_type: String(imageRef.file_type), file_index: String(imageRef.file_index),
      file_position: String(imageRef.file_position), time: imageRef.time,
    })
    return binaryResponse(`/v2/devices/capture-log/image?${params}`, {}, 'Không tải được ảnh FaceGate')
      .then(response => response.blob())
  },
  autoCheck: (start = '', end = '') => {
    const params = new URLSearchParams()
    if (start && end) {
      params.set('start', start)
      params.set('end', end)
    }
    return request(`/v2/auto-check${params.size ? `?${params}` : ''}`)
  },
  updateAutoCheck: (body) => request('/v2/auto-check/config', { method: 'PUT', body: JSON.stringify(body) }),
  runAutoCheck: () => request('/v2/auto-check/run', { method: 'POST' }),
  exportAutoCheckExcel: (start, end) => download(`/v2/auto-check/export.xlsx?${new URLSearchParams({ start, end })}`, 'VERA_Auto_Check.xlsx'),
  exportSnapshotExcel: (start, end) => download(`/v2/snapshot/export.xlsx?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`, 'VERA_ChamCong.xlsx'),
  exportComboSalesExcel: (start, end, department) => download(
    `/v2/work-schedule/combo-sales/export.xlsx?${new URLSearchParams({ start, end, department })}`,
    `VERA_Ban_Combo_${department}_${start}_${end}.xlsx`,
  ),
  importComboSalesExcel: (file, department) => upload('/v2/work-schedule/combo-sales/import.xlsx', file, { department }),
  adminChanges: (days = 7) => request(`/v2/admin/changes?days=${encodeURIComponent(days)}`),
  notificationSettings: () => request('/v2/notification-settings'),
  notificationPopup: () => request('/v2/notification-popup'),
  createNotificationGroup: body => request('/v2/notification-settings/groups', { method:'POST', body:JSON.stringify(body) }),
  deleteNotificationGroup: (key, revision) => request(`/v2/notification-settings/groups/${encodeURIComponent(key)}?revision=${revision}`, { method:'DELETE' }),
  notificationTasks: () => request('/v2/notification-settings/tasks'),
  createNotification: body => request('/v2/notification-settings', { method:'POST', body:JSON.stringify(body) }),
  orderNotifications: body => request('/v2/notification-settings/order', { method:'PUT', body:JSON.stringify(body) }),
  notificationInbox: () => request('/v2/notification-inbox'),
  notificationDetail: id => request(`/v2/notification-inbox/${encodeURIComponent(id)}`),
  readNotification: id => request(`/v2/notification-inbox/${id}/read`, { method:'POST' }),
  updateNotificationChannel: (key, channel, changes) => request(`/v2/notification-settings/${encodeURIComponent(key)}/channels/${channel}`, { method:'PUT', body:JSON.stringify(changes) }),
  routeLocalNotification: key => request(`/v2/notification-local/${encodeURIComponent(key)}`, { method:'POST' }),
  updateNotificationSetting: (key, changes) => request(`/v2/notification-settings/${encodeURIComponent(key)}`, {
    method: 'PUT', body: JSON.stringify(typeof changes === 'boolean' ? { enabled: changes } : changes),
  }),
  storagePreview: (start, end) => request(`/v2/storage/preview?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}`),
  exportStorageExcel: (start, end, dataset = 'all') => download(`/v2/storage/export.xlsx?start=${encodeURIComponent(start)}&end=${encodeURIComponent(end)}&dataset=${encodeURIComponent(dataset)}`, 'VERA_LuuTru.xlsx'),
  deleteStorageData: (body) => request('/v2/storage', { method: 'DELETE', body: JSON.stringify(body) }),
  trainingBootstrap: () => request('/v2/training/bootstrap'),
  createTrainingSession: (body) => request('/v2/training/sessions', { method: 'POST', body: JSON.stringify(body) }),
  updateTrainingSession: (id, body) => request(`/v2/training/sessions/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) }),
  saveTrainingScope: (body) => request('/v2/training/scopes', { method: 'PUT', body: JSON.stringify(body) }),
  createEvaluationCycle: (body) => request('/v2/training/cycles', { method: 'POST', body: JSON.stringify(body) }),
  changeEvaluationCycle: (id, action) => request(`/v2/training/cycles/${encodeURIComponent(id)}/${action}`, { method: 'POST' }),
  saveTrainingEvaluation: (id, body) => request(`/v2/training/evaluations/${encodeURIComponent(id)}`, { method: 'PUT', body: JSON.stringify(body) }),
  trainingReport: (employee, filters = {}) => {
    const params = new URLSearchParams()
    params.set('evaluator_role', filters.evaluator_role || 'all')
    if (filters.q?.trim()) params.set('q', filters.q.trim())
    if (filters.date_from) params.set('date_from', filters.date_from)
    if (filters.date_to) params.set('date_to', filters.date_to)
    if (filters.rating && filters.rating !== 'all') params.set('rating', filters.rating)
    params.set('page', String(filters.page || 1))
    params.set('page_size', String(filters.page_size || 50))
    return request(`/v2/training/reports/${encodeURIComponent(employee)}?${params}`)
  },
  exportTrainingEvaluation: (assignmentId, format) => download(
    `/v2/training/evaluations/${encodeURIComponent(assignmentId)}/export.${format}`,
    `VERA_DanhGia_${assignmentId}.${format}`,
  ),
  leaveOverlap: (start, end, department = '', threshold = 0.2) => {
    const params = new URLSearchParams({ start, end, threshold: String(threshold) })
    if (department) params.set('department_id', department)
    return request(`/v2/hr/leaves/overlap?${params}`)
  },
  saveTrainingNotificationRecipients: (usernames) => request('/v2/training/notification-recipients', { method: 'PUT', body: JSON.stringify({ usernames }) }),
  trainingNotifications: (channel = 'in_app') => request(`/v2/training/notifications?channel=${channel === 'popup' ? 'popup' : 'in_app'}`),
  readTrainingNotification: (id) => request(`/v2/training/notifications/${encodeURIComponent(id)}/read`, { method: 'POST' }),
  trainingNotificationDetail: (id) => request(`/v2/training/notifications/${encodeURIComponent(id)}/detail`),
  createLeave: (body) => request('/v2/leave/records', { method: 'POST', body: JSON.stringify(body) }).then(notifyLeaveChange),
  updateLeave: (recordUid, body) => request(`/v2/leave/records/${encodeURIComponent(recordUid)}`, { method: 'PATCH', body: JSON.stringify(body) }).then(notifyLeaveChange),
  deleteLeaves: (recordUids) => request('/v2/leave/records', { method: 'DELETE', body: JSON.stringify({ record_uids: recordUids }) }).then(notifyLeaveChange),
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
  birthdays: (month = new Date().getMonth() + 1) => request(`/v2/birthdays?month=${encodeURIComponent(month)}`),
  tour: (refresh = false) => request(`/v2/tour?refresh=${refresh ? 'true' : 'false'}`),
  liveTour: (refresh = false, includeHidden = false, knownRevision = null, view = 'full') => {
    const params = new URLSearchParams({
      view, refresh: refresh ? 'true' : 'false',
      include_hidden: includeHidden ? 'true' : 'false',
    })
    if (Number.isInteger(knownRevision) && knownRevision >= 0) params.set('known_revision', String(knownRevision))
    return request(`/v2/live-tour?${params}`)
  },
  liveTourCollection: (panel, query = {}) => request(`/v2/live-tour/collections/${encodeURIComponent(panel)}?${new URLSearchParams(Object.entries(query).filter(([,value])=>value !== '' && value != null))}`),
  liveTourAction: async (body) => {
    // Release the operator UI if the network or a database connection stalls.
    // The caller retains body.idempotency_key for a safe retry after a reload.
    const signal = AbortSignal.timeout(30000)
    try {
      return await request('/v2/live-tour/action', { method: 'POST', body: JSON.stringify(body), signal })
    } catch (error) {
      if (signal.aborted) throw new Error('Chưa xác nhận được thao tác sau 30 giây. Hãy tải bản đã lưu để kiểm tra kết quả trước khi thử lại.')
      throw error
    }
  },
  liveTourRecovery: () => request('/v2/live-tour/recovery'),
  retryLiveTourRecovery: () => request('/v2/live-tour/recovery/retry', { method: 'POST' }),
  uiLayout: () => request('/v2/ui-layout'),
  saveUiLayout: (body) => request('/v2/ui-layout', { method: 'PUT', body: JSON.stringify(body) }),
  previewBoardHistoryCleanup: (body) => request('/v2/live-tour/board-history/cleanup-preview', { method: 'POST', body: JSON.stringify(body) }),
  deleteBoardHistory: (body) => request('/v2/live-tour/board-history', { method: 'DELETE', body: JSON.stringify(body) }),
  liveTourReports: () => request('/v2/live-tour/reports'),
  liveTourBoardHistory: (query = {}) => {
    const params = new URLSearchParams()
    if (query.date_from) params.set('date_from', query.date_from)
    if (query.date_to) params.set('date_to', query.date_to)
    if (query.employee?.trim()) params.set('employee', query.employee.trim())
    return request(`/v2/live-tour/board-history${params.size ? `?${params}` : ''}`)
  },
  exportLiveTourBoardHistory: (query = {}) => {
    const params = new URLSearchParams()
    if (query.date_from) params.set('date_from', query.date_from)
    if (query.date_to) params.set('date_to', query.date_to)
    if (query.employee?.trim()) params.set('employee', query.employee.trim())
    return download(`/v2/live-tour/board-history/export.xlsx${params.size ? `?${params}` : ''}`, 'VERA_LichSu_LiveTour.xlsx')
  },
  liveTourMyTips: () => request('/v2/live-tour/my-tips'),
  spaCustomers: () => request('/v2/live-tour/customers'),
  spaSettings: () => request('/v2/live-tour/settings'),
  liveTourCustomerHistory: (customerId) => request(`/v2/live-tour/customers/${encodeURIComponent(customerId)}/history`),
  exportLiveTourExcel: (kind = 'board', query = {}) => {
    const params = liveTourExportParams(kind, query)
    return download(`/v2/live-tour/export.xlsx?${params}`, `VeraSpa_LiveTour_${kind}.xlsx`)
  },
  importLiveTourExcel: (file, expectedRevision) => upload('/v2/live-tour/import.xlsx', file, { expected_revision: expectedRevision }),
  scheduleShiftSettings: () => {
    const day = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
    return request(`/v2/work-schedule?start=${day}&end=${day}`)
  },
  saveScheduleShifts: body => request('/v2/work-schedule/shifts', { method: 'PUT', body: JSON.stringify(body) }),
  ktvShifts: () => request('/v2/staff/ktv-shifts'),
  saveKtvShift: (id, body) => request(`/v2/staff/ktv-shifts${id ? `/${encodeURIComponent(id)}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) }),
  deleteKtvShift: (id, revision) => request(`/v2/staff/ktv-shifts/${encodeURIComponent(id)}?expected_revision=${revision}`, { method: 'DELETE' }),
  ktvCycles: () => request('/v2/staff/ktv-cycles'),
  saveKtvCycle: (id, body) => request(`/v2/staff/ktv-cycles${id ? `/${encodeURIComponent(id)}` : ''}`, { method: id ? 'PUT' : 'POST', body: JSON.stringify(body) }),
  deleteKtvCycle: (id, revision) => request(`/v2/staff/ktv-cycles/${encodeURIComponent(id)}?expected_revision=${revision}`, { method: 'DELETE' }),
  readLiveTourPng: async (query = {}) => {
    const params = liveTourExportParams('board', query)
    const response = await binaryResponse(`/v2/live-tour/export.png?${params}`, { cache: 'no-store' })
    return response.blob()
  },
  tourSource: () => request('/v2/tour/source'),
  saveTourSource: (body) => request('/v2/tour/source', { method: 'PUT', body: JSON.stringify(body) }),
  syncTourLeave: (action) => request('/v2/tour-leave-sync', {
    method: 'POST', body: JSON.stringify({ action }),
  }),
  exportLeaveExcel: (start, end, employee = '') => {
    const params = new URLSearchParams({ start, end })
    if (employee.trim()) params.set('employee', employee.trim())
    return download(`/v2/leave/export.xlsx?${params}`, `vera-lich-nghi-${start}-${end}.xlsx`)
  },
  syncLeaveSource: () => request('/v2/leave/source-sync', { method: 'POST' }).then(notifyLeaveChange),
  importLeaveExcel: (file) => upload('/v2/leave/import.xlsx', file).then(notifyLeaveChange),
}
