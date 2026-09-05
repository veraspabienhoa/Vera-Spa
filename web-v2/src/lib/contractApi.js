import { getCurrentSession, refreshCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function authorizedFetch(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  let session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  let response = await fetch(`${apiBase}${path}`, { ...options, headers })
  if (response.status === 401 && session?.refresh_token) {
    session = await refreshCurrentSession(session)
    if (session?.access_token) {
      headers.set('Authorization', `Bearer ${session.access_token}`)
      response = await fetch(`${apiBase}${path}`, { ...options, headers })
    }
  }
  return response
}

async function jsonRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await authorizedFetch(path, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

async function exportPdf(body) {
  const response = await authorizedFetch('/v2/contracts/1/export.pdf', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  }
  const blob = await response.blob()
  const disposition = response.headers.get('content-disposition') || ''
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
  const filename = encoded ? decodeURIComponent(encoded.replace(/^"|"$/g, '')) : 'Hop_Dong_KTV.pdf'
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = filename
  document.body.appendChild(anchor)
  anchor.click()
  anchor.remove()
  window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  return { count: Number(response.headers.get('x-contract-count') || 0), filename }
}

export const contractApi = {
  overview: () => jsonRequest('/v2/contracts/1'),
  saveSettings: (body) => jsonRequest('/v2/contracts/1/settings', {
    method: 'PUT', body: JSON.stringify(body),
  }),
  exportPdf,
}
