import { createClient } from '@supabase/supabase-js'
import { apiBase } from './apiConfig'
import { authJsonRequest } from './authTransport'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim()
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim()
const API_SESSION_KEY = 'vera-v2-api-auth-session'
const apiAuthListeners = new Set()
let refreshState = null
let volatileApiSession = null
let authEpoch = 0

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

const parseApiSession = (raw) => {
  try {
    const session = raw ? JSON.parse(raw) : null
    return session?.access_token && session?.refresh_token && session?.user ? session : null
  } catch {
    return null
  }
}

const readStoredApiSession = () => {
  try { return parseApiSession(window.localStorage.getItem(API_SESSION_KEY)) } catch { return null }
}

const readApiSession = () => readStoredApiSession() || volatileApiSession

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

const clearApiSession = (expectedRefreshToken = '') => {
  const stored = readStoredApiSession()
  const currentToken = stored?.refresh_token || volatileApiSession?.refresh_token || ''
  if (expectedRefreshToken && currentToken && currentToken !== expectedRefreshToken) {
    volatileApiSession = stored || volatileApiSession
    return false
  }
  authEpoch += 1
  volatileApiSession = null
  try { window.localStorage.removeItem(API_SESSION_KEY) } catch { /* private browsing may block storage */ }
  return true
}

const apiAuthRequest = async (path, body) => {
  const { response, payload } = await authJsonRequest(`${apiBase}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!response.ok) {
    const error = new Error(payload?.detail || payload?.message || 'Không đăng nhập được vào máy chủ VERA.')
    error.status = response.status
    throw error
  }
  if (path !== '/v2/auth/logout' && (
    typeof payload?.access_token !== 'string' || !payload.access_token ||
    typeof payload?.refresh_token !== 'string' || !payload.refresh_token || !payload?.user?.id
  )) {
    throw Object.assign(new Error('Máy chủ VERA trả phiên đăng nhập không hợp lệ. Vui lòng thử lại.'), { status: 502 })
  }
  return payload
}

export async function signInWithVeraPassword(username, password) {
  const cleanUsername = String(username || '').trim()
  if (!cleanUsername || !password) throw new Error('Vui lòng nhập tên đăng nhập và mật khẩu.')

  try {
    const payload = await apiAuthRequest('/v2/auth/login', { username: cleanUsername, password })
    authEpoch += 1
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
  const attemptedToken = session.refresh_token
  if (refreshState?.token === attemptedToken) return refreshState.promise

  const epoch = authEpoch
  const state = { token: attemptedToken, epoch, promise: null }
  state.promise = apiAuthRequest('/v2/auth/refresh', { refresh_token: attemptedToken })
    .then((payload) => {
      const current = readStoredApiSession() || readApiSession()
      if (authEpoch !== epoch || current?.refresh_token !== attemptedToken) return current
      return saveApiSession(payload, 'TOKEN_REFRESHED')
    })
    .finally(() => {
      if (refreshState === state) refreshState = null
    })
  refreshState = state
  return state.promise
}

export async function refreshCurrentSession(session = readApiSession()) {
  if (!session?.refresh_token) return null
  const attemptedToken = session.refresh_token
  try {
    return await refreshApiSession(session)
  } catch (error) {
    const current = readStoredApiSession() || readApiSession()
    if (current?.refresh_token && current.refresh_token !== attemptedToken) return current
    // Only a confirmed rejection revokes local credentials. A rollout, network
    // failure or timeout must remain retryable without losing the refresh token.
    if ((error.status === 401 || error.status === 403) && clearApiSession(attemptedToken)) notifyApiAuth('SIGNED_OUT', null)
    throw error
  }
}

export async function getCurrentSession() {
  const apiSession = readApiSession()
  if (apiSession) {
    const now = Math.floor(Date.now() / 1000)
    if (Number(apiSession.expires_at || 0) > now + 90) return apiSession
    try {
      return await refreshCurrentSession(apiSession)
    } catch (error) {
      const current = readStoredApiSession() || readApiSession()
      if (current?.refresh_token && current.refresh_token !== apiSession.refresh_token) return current
      if (error.status === 401 || error.status === 403 || !current) return null
      if (Number(current.expires_at || 0) > Math.floor(Date.now() / 1000) + 5) return current
      // Do not return an expired access token or a cached profile as proof of
      // authentication. The UI offers retry while keeping business pages gated.
      throw error
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
  if (clearApiSession(session?.refresh_token || '')) notifyApiAuth('SIGNED_OUT', null)
  if (session?.refresh_token) {
    await apiAuthRequest('/v2/auth/logout', { refresh_token: session.refresh_token }).catch(() => {})
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('storage', (event) => {
    if (event.key !== API_SESSION_KEY) return
    authEpoch += 1
    volatileApiSession = parseApiSession(event.newValue)
    notifyApiAuth(volatileApiSession ? 'SIGNED_IN' : 'SIGNED_OUT', volatileApiSession)
  })
}
