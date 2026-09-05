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

function identityKey(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd').replace(/Đ/g, 'D').toLocaleLowerCase('vi')
    .replace(/[^a-z0-9]+/g, ' ').trim().replace(/\s+/g, ' ')
}

async function validateDraftIdentity(media, fullName, cccdNumber) {
  if (!media?.portrait) throw new Error('Phải có ảnh nhân viên tỷ lệ 3:4 trước khi lưu.')
  if (!media?.front || !media?.back) throw new Error('Phải tải hoặc chụp đủ mặt trước và mặt sau CCCD trước khi lưu.')
  const results = await Promise.all([
    staffSecurityApi.extractIdentity(media.front),
    staffSecurityApi.extractIdentity(media.back),
  ])
  const extracted = {}
  results.forEach((result) => Object.entries(result.extracted_fields || {}).forEach(([key, value]) => {
    if (value && !extracted[key]) extracted[key] = value
  }))
  const declaredName = String(fullName || '').trim()
  const declaredNumber = String(cccdNumber || '').replace(/\D/g, '')
  if (!extracted.full_name) throw new Error('Không đọc rõ Họ và tên trên ảnh CCCD; vui lòng chụp hoặc tải lại ảnh rõ hơn.')
  if (!extracted.cccd_number) throw new Error('Không đọc rõ Số Căn cước trên ảnh CCCD; vui lòng chụp hoặc tải lại ảnh rõ hơn.')
  if (identityKey(extracted.full_name) !== identityKey(declaredName)) {
    throw new Error(`Họ và tên trên CCCD (${extracted.full_name}) không khớp với Họ và tên đã khai (${declaredName}).`)
  }
  if (String(extracted.cccd_number).replace(/\D/g, '') !== declaredNumber) {
    throw new Error(`Số Căn cước trên CCCD (${extracted.cccd_number}) không khớp với số đã khai (${declaredNumber}).`)
  }
  return extracted
}

export const staffSecurityApi = {
  validateDraftIdentity,
  resetPassword: (username, newPassword) => jsonRequest(`/v2/staff/${encodeURIComponent(username)}/reset-password`, {
    method: 'POST',
    body: JSON.stringify({ new_password: newPassword }),
  }),
  identityMetadata: (username) => jsonRequest(`/v2/staff/${encodeURIComponent(username)}/identity`),
  extractIdentity: async (blob) => {
    const response = await authorizedFetch('/v2/staff/identity/ocr', {
      method: 'POST',
      headers: { 'Content-Type': blob.type || 'image/webp' },
      body: blob,
    })
    const payload = await response.json().catch(() => ({}))
    if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
    return payload
  },
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
