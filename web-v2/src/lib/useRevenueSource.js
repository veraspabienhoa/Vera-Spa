import { useCallback, useEffect, useRef, useState } from 'react'
import { getCurrentSession } from './supabase'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

export async function revenueSourceRequest(body, signal) {
  const session = await getCurrentSession()
  const response = await fetch(`${apiBase}/v2/revenue/source`, {
    method: body ? 'PUT' : 'GET', signal, cache: 'no-store',
    headers: { Authorization: `Bearer ${session?.access_token || ''}`, ...(body ? { 'Content-Type': 'application/json' } : {}) },
    ...(body ? { body: JSON.stringify(body) } : {}),
  })
  const result = await response.json()
  // Frontend may deploy before the manual VPS rollout. Keep existing Manual
  // usable, but do not advertise or enable a shared mode on the old server.
  if (!body && response.status === 404) return { source: 'manual', revision: 0, supported: false }
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
  return { ...result, supported: true }
}

export default function useRevenueSource() {
  const [shared, setShared] = useState(null)
  const [changing, setChanging] = useState(false)
  const [error, setError] = useState('')
  const active = useRef(null)
  const accept = useCallback(result => {
    setShared(current => current && (current.revision > result.revision || (current.revision === result.revision && current.source === result.source && current.supported === result.supported && current.period_report_version === result.period_report_version)) ? current : result)
    setError('')
  }, [])
  const refresh = useCallback(async () => {
    active.current?.abort()
    const controller = new AbortController()
    active.current = controller
    try {
      const result = await revenueSourceRequest(null, controller.signal)
      if (!controller.signal.aborted) accept(result)
    } catch (err) {
      if (!controller.signal.aborted) setError(err.message || 'Không kiểm tra được chế độ Doanh thu.')
    }
  }, [accept])
  useEffect(() => {
    const visibleRefresh = () => { if (document.visibilityState !== 'hidden') void refresh() }
    void refresh()
    const timer = setInterval(visibleRefresh, 30000)
    document.addEventListener('visibilitychange', visibleRefresh)
    window.addEventListener('focus', visibleRefresh)
    return () => { clearInterval(timer); active.current?.abort(); document.removeEventListener('visibilitychange', visibleRefresh); window.removeEventListener('focus', visibleRefresh) }
  }, [refresh])
  const change = async source => {
    if (!shared?.supported || changing) return
    setChanging(true)
    active.current?.abort()
    try { accept(await revenueSourceRequest({ source, revision: shared.revision })) }
    catch (err) { await refresh(); setError(err.message || 'Không đổi được chế độ Doanh thu.') }
    finally { setChanging(false) }
  }
  return { reportVersion: shared?.period_report_version || 0, source: shared?.source || 'manual', revision: shared?.revision, ready: Boolean(shared), supported: Boolean(shared?.supported), changing, error, change, refresh }
}
