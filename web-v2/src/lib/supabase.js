import { createClient } from '@supabase/supabase-js'

const supabaseUrl = import.meta.env.VITE_SUPABASE_URL?.trim()
const supabaseAnonKey = import.meta.env.VITE_SUPABASE_ANON_KEY?.trim()
const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const API_SESSION_KEY = 'vera-v2-api-auth-session'
const apiAuthListeners = new Set()
let refreshPromise = null
let volatileApiSession = null

export const isSupabaseConfigured = Boolean(supabaseUrl && supabaseAnonKey)
export const isAuthConfigured = Boolean(apiBase || isSupabaseConfigured)

export const supabase = isSupabaseConfigured
  ? createClient(supabaseUrl, supabaseAnonKey, {
      auth: {
        persistSession: true,
        autoRefreshToken: true,
        detectSessionInUrl: true,
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
  if (!apiBase) throw new Error('Máy chủ VERA chưa được cấu hình.')
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

const directSupabaseLogin = async (username, password) => {
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')
  const { data: bridge, error: bridgeError } = await supabase.functions.invoke('vera-v2-login', {
    body: { username, password },
  })
  if (bridgeError) {
    let detail = bridgeError.message
    try {
      const responseBody = await bridgeError.context?.json?.()
      detail = responseBody?.message || detail
    } catch {
      // Keep the SDK error message when the Edge Function response has no JSON body.
    }
    throw new Error(detail || 'Không xác thực được tài khoản VERA.')
  }
  if (!bridge?.email || !bridge?.password) {
    throw new Error(bridge?.message || 'Không xác thực được tài khoản VERA.')
  }
  const { data, error } = await supabase.auth.signInWithPassword({
    email: bridge.email,
    password: bridge.password,
  })
  if (error) throw error
  clearApiSession()
  return data.session
}

export async function signInWithVeraPassword(username, password) {
  const cleanUsername = String(username || '').trim()
  if (!cleanUsername || !password) throw new Error('Vui lòng nhập tên đăng nhập và mật khẩu.')

  if (apiBase) {
    try {
      const payload = await apiAuthRequest('/v2/auth/login', { username: cleanUsername, password })
      return saveApiSession(payload)
    } catch (error) {
      // Invalid/locked/inactive accounts must not be retried through another path.
      if (Number(error?.status || 0) >= 400 && Number(error?.status || 0) < 500) throw error
      if (!supabase) throw error
    }
  }
  return directSupabaseLogin(cleanUsername, password)
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
  if (!supabase) return null
  const { data, error } = await supabase.auth.getSession()
  if (error) throw error
  return data.session
}

export function onVeraAuthStateChange(listener) {
  apiAuthListeners.add(listener)
  const supabaseListener = supabase?.auth.onAuthStateChange((event, session) => {
    if (!readApiSession()) listener(event, session)
  })
  return () => {
    apiAuthListeners.delete(listener)
    supabaseListener?.data?.subscription?.unsubscribe()
  }
}

export async function signOutVera() {
  const hadApiSession = Boolean(readApiSession())
  clearApiSession()
  if (hadApiSession) notifyApiAuth('SIGNED_OUT', null)
  if (supabase) await supabase.auth.signOut({ scope: 'local' }).catch(() => {})
}
