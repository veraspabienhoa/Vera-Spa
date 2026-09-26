import { useEffect, useRef } from 'react'

export const PAGE_REFRESH_EVENT = 'vera:page-refresh'
export const PAGE_REFRESH_ERROR = 'vera:page-refresh-error'
const CHECK_REFRESH_EVENT = 'vera:page-refresh-check'

export function requestPageRefresh(target = window) {
  if (!target.dispatchEvent(new target.Event(CHECK_REFRESH_EVENT, { cancelable: true }))) return false
  target.dispatchEvent(new target.Event(PAGE_REFRESH_EVENT))
  return true
}

// Each mounted business panel refreshes its existing data loader. Keeping the
// React tree preserves filters, scroll containers, focus and form state.
export default function usePageRefresh(refresh, blocked = () => false) {
  const latest = useRef({ refresh, blocked })
  latest.current = { refresh, blocked }
  useEffect(() => {
    let active = true, pending = false
    const check = event => { if (pending || latest.current.blocked()) event.preventDefault() }
    const handle = async () => {
      if (pending || latest.current.blocked()) return
      pending = true
      try { await latest.current.refresh() }
      catch (error) {
        if (active) window.dispatchEvent(new window.CustomEvent(PAGE_REFRESH_ERROR, { detail: error?.message || 'Không tải lại được dữ liệu. Vui lòng thử lại.' }))
      } finally { pending = false }
    }
    window.addEventListener(CHECK_REFRESH_EVENT, check)
    window.addEventListener(PAGE_REFRESH_EVENT, handle)
    return () => {
      active = false
      window.removeEventListener(CHECK_REFRESH_EVENT, check)
      window.removeEventListener(PAGE_REFRESH_EVENT, handle)
    }
  }, [])
}
