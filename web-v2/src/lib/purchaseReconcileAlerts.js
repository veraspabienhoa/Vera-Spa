import { getCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const CHECK_INTERVAL_MS = 15 * 60 * 1000
let started = false
let running = false

async function checkPurchaseReconcileAlerts() {
  if (!apiBase || running || document.visibilityState === 'hidden') return
  running = true
  try {
    const session = await getCurrentSession()
    if (!session?.access_token) return
    await fetch(`${apiBase}/v2/revenue/purchase-reconcile/alert-check`, {
      headers: { Authorization: `Bearer ${session.access_token}` },
      cache: 'no-store',
    })
  } catch {
    // Best-effort background check. Revenue and other pages must remain usable
    // even if Google Drive, PostgreSQL, or push delivery is temporarily offline.
  } finally {
    running = false
  }
}

export function startPurchaseReconcileAlertWatcher() {
  if (started || !apiBase) return
  started = true

  window.setTimeout(() => { void checkPurchaseReconcileAlerts() }, 15_000)
  window.setInterval(() => { void checkPurchaseReconcileAlerts() }, CHECK_INTERVAL_MS)
  document.addEventListener('visibilitychange', () => {
    if (document.visibilityState === 'visible') void checkPurchaseReconcileAlerts()
  })
}
