import { getCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function authorizedFetch(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  return fetch(`${apiBase}${path}`, { ...options, headers })
}

async function jsonRequest(path, options = {}) {
  const headers = new Headers(options.headers || {})
  if (options.body && !headers.has('Content-Type')) headers.set('Content-Type', 'application/json')
  const response = await authorizedFetch(path, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

export const staffSecurityApi = {
  resetPassword: (username, newPassword) => jsonRequest(`/v2/staff/${encodeURIComponent(username)}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  }),
  identityMetadata: (username) => jsonRequest(`/v2/staff/${encodeURIComponent(username)}/identity`),
  identityBlob: async (username, side) => {
    const response = await authorizedFetch(`/v2/staff/${encodeURIComponent(username)}/identity/${encodeURIComponent(side)}`)
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
    }
    return response.blob()
  },
  uploadIdentity: async (username, side, blob) => {
    const response = await authorizedFetch(`/v2/staff/${encodeURIComponent(username)}/identity/${encodeURIComponent(side)}`, {
      method: 'PUT',
      headers: { 'Content-Type': blob.type || 'image/webp' },
      body: blob,
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
    return payload
  },
  deleteIdentity: (username, side) => jsonRequest(`/v2/staff/${encodeURIComponent(username)}/identity/${encodeURIComponent(side)}`, {
    method: 'DELETE',
  }),
  exportProfilePdf: async (username) => {
    const response = await authorizedFetch(`/v2/staff/${encodeURIComponent(username)}/profile.pdf`)
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
    }
    const blob = await response.blob()
    const disposition = response.headers.get('content-disposition') || ''
    const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1]
    const filename = encoded ? decodeURIComponent(encoded) : `Ho_So_${username}.pdf`
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = filename
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  },
}
