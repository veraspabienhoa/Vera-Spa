import { getCurrentSession, onVeraAuthStateChange } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const CHECK_INTERVAL_MS = 15 * 60 * 1000
let started = false
let running = false
let verifiedSession = null

async function checkPurchaseReconcileAlerts() {
  if (!apiBase || running || !verifiedSession?.access_token || document.visibilityState === 'hidden') return
  running = true
  try {
    const session = await getCurrentSession()
    if (!session?.access_token || session.refresh_token !== verifiedSession.refresh_token) return
    await fetch(`${apiBase}/v2/revenue/purchase-reconcile/alert-check`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: 'no-store',
    })
  } catch {
    // Best-effort background check. Revenue and other pages must remain usable
    // even if Google Drive, PostgreSQL, auth refresh, or push delivery is temporarily offline.
  } finally {
    running = false
  }
}

export function markPurchaseReconcileAlertWatcherSession(session) {
  verifiedSession = session?.access_token ? session : null
  if (verifiedSession) void checkPurchaseReconcileAlerts()
}

export function startPurchaseReconcileAlertWatcher() {
  if (started || !apiBase) return
  started = true

  onVeraAuthStateChange((_event, session) => {
    markPurchaseReconcileAlertWatcherSession(session)
  })
  window.setInterval(() => { void checkPurchaseReconcileAlerts() }, CHECK_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void checkPurchaseReconcileAlerts()
  })
}