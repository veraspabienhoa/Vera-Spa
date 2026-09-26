import { useEffect, useRef, useState } from 'react'
import { getCurrentSession } from './supabase'
import { createVisiblePoller } from './visiblePoller'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

export function watchRevenueChanges(load, { changed, blocked, failed, stale = () => false, ...options }) {
  let seen = null
  return createVisiblePoller(async () => {
    try {
      const revision = await load()
      failed('')
      // Do not consume a revision while a form/save/read is still in progress.
      if (revision && (revision !== seen || stale()) && !blocked()) { seen = revision; changed() }
    } catch (error) { if (error?.name !== 'AbortError') failed('Tạm mất kết nối cập nhật Doanh thu. Hệ thống sẽ tự thử lại.') }
  }, { interval: 5000, ...options })
}

export default function useRevenueRealtime(enabled, blocked, changed, stale = false) {
  const latest = useRef({ blocked, changed, stale })
  latest.current = { blocked, changed, stale }
  const [error, setError] = useState('')
  useEffect(() => {
    if (!enabled) return undefined
    const controller = new AbortController()
    const poller = watchRevenueChanges(async () => {
      const session = await getCurrentSession()
      const response = await fetch(`${apiBase}/v2/revenue/revision`, {
        signal: controller.signal, cache: 'no-store',
        headers: { Authorization: `Bearer ${session?.access_token || ''}` },
      })
      if (!response.ok) throw new Error('Revenue revision unavailable')
      const result = await response.json()
      return controller.signal.aborted ? null : result.revision
    }, {
      blocked: () => latest.current.blocked,
      stale: () => latest.current.stale,
      changed: () => latest.current.changed(),
      failed: value => { if (!controller.signal.aborted) setError(value) },
    })
    return () => { controller.abort(); poller.stop() }
  }, [enabled])
  return enabled ? error : ''
}
