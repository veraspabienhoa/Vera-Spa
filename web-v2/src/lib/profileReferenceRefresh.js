import { getCurrentSession, refreshCurrentSession } from './supabase'
import { apiErrorMessage } from './apiError'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

export async function refreshProfileReferenceData(provinceCode = '') {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  let session = await getCurrentSession()
  const headers = new Headers({ 'Content-Type': 'application/json', 'Cache-Control': 'no-cache' })
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const params = new URLSearchParams({ refresh: 'true', t: String(Date.now()) })
  if (provinceCode !== '' && provinceCode !== null && provinceCode !== undefined) params.set('province_code', String(provinceCode))

  let response = await fetch(`${apiBase}/v2/profile/reference-data?${params}`, { headers })
  if (response.status === 401 && session?.refresh_token) {
    session = await refreshCurrentSession(session)
    if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
    response = await fetch(`${apiBase}/v2/profile/reference-data?${params}`, { headers })
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(apiErrorMessage(payload, response.status))
  return payload
}
