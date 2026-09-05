import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim()
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim()
// api.veraspa.vn is the canonical production backend. Keep an env override for
// local/staging builds, but never let a production browser silently fall back
// to calling the Supabase Edge Function directly when the API has a transient
// error. That fallback hid the real backend failure behind the generic SDK
// message "Failed to send a request to the Edge Function".
const apiBase = (import.meta.env.VITE_VERA_API_BASE_URL?.trim() || 'https://api.veraspa.vn').replace(/\/$/, '')
const API_SESSION_KEY = 'vera-v2-api-auth-session'
const apiAuthListeners = new Set()
let refreshPromise = null
let volatileApiSession = null

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey)
export const isAuthConfigured = Boolean(apiBase)

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        // Authentication is owned by the Vera API. Keep this client only for
        // legacy data RPCs and never load, refresh, or create a browser-side
        // Supabase Auth session.
        persistSession: false,
        autoRefreshToken: false,
        detectSessionInUrl: false,
      },
    })
  : null

const readApiSession = () => {
  if (volatileApiSession) return volatileApiSession
  try {
    const raw = window.localStorage.getItem(API_SESSION_KEY)
    const session = raw ? JSON.parse(raw) : null
    return session?.access_token && session?.refresh_token && session?.user ? session : null
  } catch {
    return null
  }
}

const notifyApiAuth = (event, session) => {
  apiAuthListeners.forEach((listener) => {
    try { listener(event, session) } catch { /* one listener must not block the others */ }
  })
}

const saveApiSession = (payload, event = 'SIGNED_IN') => {
  const expiresIn = Number(payload?.expires_in || 3600)
  const session = {
    access_token: payload.access_token,
    refresh_token: payload.refresh_token,
    token_type: payload.token_type || 'bearer',
    expires_in: expiresIn,
    expires_at: Number(payload.expires_at || Math.floor(Date.now() / 1000) + expiresIn),
    user: payload.user,
    vera_profile: payload.vera_profile || null,
  }
  volatileApiSession = session
  try { window.localStorage.setItem(API_SESSION_KEY, JSON.stringify(session)) } catch { /* keep the in-memory session */ }
  notifyApiAuth(event, session)
  return session
}

const clearApiSession = () => {
  volatileApiSession = null
  try { window.localStorage.removeItem(API_SESSION_KEY) } catch { /* private browsing may block storage */ }
}

const apiAuthRequest = async (path, body) => {
  const response = await fetch(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) {
    const error = new Error(payload.detail || payload.message || 'Không đăng nhập được vào máy chủ VERA.')
    error.status = response.status
    throw error
  }
  return payload
}

export async function signInWithVeraPassword(username, password) {
  const cleanUsername = String(username || '').trim()
  if (!cleanUsername || !password) throw new Error('Vui lòng nhập tên đăng nhập và mật khẩu.')

  try {
    const payload = await apiAuthRequest('/v2/auth/login', { username: cleanUsername, password })
    return saveApiSession(payload)
  } catch (error) {
    // Authentication is owned by api.veraspa.vn. Do not retry through the
    // browser-facing Edge Function: it creates a second failure mode and can
    // replace a useful API error with a generic network message.
    if (error instanceof TypeError) {
      throw new Error('Không kết nối được máy chủ VERA. Vui lòng thử lại sau ít phút.')
    }
    throw error
  }
}

const refreshApiSession = async (session) => {
  if (!refreshPromise) {
    refreshPromise = apiAuthRequest('/v2/auth/refresh', { refresh_token: session.refresh_token })
      .then((payload) => saveApiSession(payload, 'TOKEN_REFRESHED'))
      .finally(() => { refreshPromise = null })
  }
  return refreshPromise
}

export async function refreshCurrentSession(session = readApiSession()) {
  if (!session?.refresh_token) return null
  try {
    return await refreshApiSession(session)
  } catch (error) {
    clearApiSession()
    notifyApiAuth('SIGNED_OUT', null)
    throw error
  }
}

export async function getCurrentSession() {
  const apiSession = readApiSession()
  if (apiSession) {
    const now = Math.floor(Date.now() / 1000)
    if (Number(apiSession.expires_at || 0) > now + 90) return apiSession
    try {
      return await refreshApiSession(apiSession)
    } catch {
      if (Number(apiSession.expires_at || 0) > now + 5) return apiSession
      clearApiSession()
    }
  }
  return null
}

export function onVeraAuthStateChange(listener) {
  apiAuthListeners.add(listener)
  return () => apiAuthListeners.delete(listener)
}

export async function signOutVera() {
  const session = readApiSession()
  // Local logout must be immediate even if the revoke request is slow or the
  // API is temporarily unreachable. Server-side revocation remains best effort.
  clearApiSession()
  if (session) notifyApiAuth('SIGNED_OUT', null)
  if (session?.refresh_token) {
    await apiAuthRequest('/v2/auth/logout', { refresh_token: session.refresh_token }).catch(() => {})
  }
}
