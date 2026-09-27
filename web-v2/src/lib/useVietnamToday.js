import { useEffect, useState } from 'react'
import { createVisiblePoller } from './visiblePoller'

export function vietnamToday() {
  const parts = new Intl.DateTimeFormat('en-US', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const values = Object.fromEntries(parts.map(part => [part.type, part.value]))
  return `${values.year}-${values.month}-${values.day}`
}

export default function useVietnamToday() {
  const [today, setToday] = useState(vietnamToday)
  useEffect(() => {
    const poller = createVisiblePoller(() => setToday(vietnamToday()), { interval: 30_000 })
    window.addEventListener('focus', poller.refresh)
    return () => { window.removeEventListener('focus', poller.refresh); poller.stop() }
  }, [])
  return today
}
