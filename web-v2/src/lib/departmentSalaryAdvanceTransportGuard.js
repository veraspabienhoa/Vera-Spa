const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

function clean(value) {
  return String(value || '').trim()
}

function targetRequest(url, method) {
  if (!['POST', 'PUT'].includes(method)) return false
  return [
    '/v2/department-payroll/combined/draft',
    '/v2/department-payroll/combined/complete',
    '/v2/department-payroll/combined/export.xlsx',
  ].some((path) => url.includes(path))
}

export function startDepartmentSalaryAdvanceTransportGuard() {
  if (window.__veraDepartmentSalaryAdvanceTransportGuardStarted) return
  window.__veraDepartmentSalaryAdvanceTransportGuardStarted = true
  const originalFetch = window.fetch.bind(window)

  window.fetch = async (input, init = {}) => {
    const url = typeof input === 'string' ? input : input?.url || ''
    const method = String(init?.method || (typeof input !== 'string' ? input?.method : '') || 'GET').toUpperCase()
    if (!API_BASE || !targetRequest(url, method) || typeof init.body !== 'string') {
      return originalFetch(input, init)
    }

    let payload
    try {
      payload = JSON.parse(init.body)
    } catch {
      return originalFetch(input, init)
    }
    if (!payload?.month || !Array.isArray(payload.rows)) return originalFetch(input, init)

    try {
      const response = await originalFetch(`${API_BASE}/v2/department-payroll/advances?month=${encodeURIComponent(payload.month)}`, {
        method: 'GET',
        headers: init.headers,
      })
      if (response.ok) {
        const advancePayload = await response.json().catch(() => ({}))
        const byEmployee = advancePayload?.summary?.by_employee || {}
        payload.rows = payload.rows.map((row) => ({
          ...row,
          advance: Number(byEmployee?.[clean(row?.employee_username)]?.payroll_total || 0),
        }))
        return originalFetch(input, { ...init, body: JSON.stringify(payload) })
      }
    } catch {
      // Keep the original payroll request available if the ledger lookup is temporarily unavailable.
    }
    return originalFetch(input, init)
  }
}
