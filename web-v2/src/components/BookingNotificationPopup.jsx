import NotificationModal from './NotificationModal'
import { useEffect, useRef, useState } from 'react'
import { BellRing, X } from 'lucide-react'
import { subscribeNotificationFeed } from '../lib/notificationFeed'
import './BookingNotificationPopup.css'

const keyOf = row => String(row.payload?.tag || row.id || '')
const allowed = config => config?.enabled !== false && config?.channel_enabled?.popup !== false

export default function BookingNotificationPopup({ user, onOpen }) {
  const [rows, setRows] = useState([])
  const dismissed = useRef(new Set())
  const account = user?.id || user?.username || user?.employee_username || ''
  const locked = Boolean(user?.must_change_password)
  const storageKey = `vera-booking-popup:${account}`
  useEffect(() => {
    setRows([])
    dismissed.current = new Set()
    if (!account || locked) return undefined
    try {
      const saved = JSON.parse(sessionStorage.getItem(storageKey) || '[]')
      if (Array.isArray(saved)) dismissed.current = new Set(saved.filter(key => typeof key === 'string').slice(-200))
    } catch { /* Private browsing can disable session storage. */ }
    const unsubscribe = subscribeNotificationFeed(result => {
      const config = (result.settings || []).find(item => item.key === 'live_tour_booking')
      const unique = new Map()
      if (allowed(config)) for (const row of result.popup || []) {
        const key = keyOf(row)
        if (row.payload?.kind === 'live_tour_booking' && key && !row.read_at && !dismissed.current.has(key)) unique.set(key, row)
      }
      setRows([...unique.values()])
    })
    const changed = event => {
      if (event.detail?.key === 'live_tour_booking' && !allowed(event.detail)) setRows([])
    }
    window.addEventListener('vera-notification-settings-changed', changed)
    return () => { unsubscribe(); window.removeEventListener('vera-notification-settings-changed', changed) }
  }, [account, locked, storageKey])

  const dismiss = row => {
    dismissed.current.add(keyOf(row))
    dismissed.current = new Set([...dismissed.current].slice(-200))
    try { sessionStorage.setItem(storageKey, JSON.stringify([...dismissed.current])) } catch { /* Keep the in-memory dismissal. */ }
    setRows(current => current.filter(item => keyOf(item) !== keyOf(row)))
  }
  if (!account || locked || !rows.length) return null
  const row = rows[0]
  return <NotificationModal key={keyOf(row)} title="Booking cho nhân viên" onClose={() => dismiss(row)}><aside className="booking-notification-popup" aria-label="Booking cho nhân viên" role="status" aria-live="polite" aria-atomic="true">
    <BellRing size={23} aria-hidden="true"/>
    <div className="booking-notification-copy"><strong>Booking mới{rows.length > 1 ? ` · ${rows.length}` : ''}</strong><p>{row.payload.body}</p></div>
    <button type="button" className="booking-notification-close" aria-label="Đóng thông báo booking" onClick={() => dismiss(row)}><X size={22}/></button>
    <button type="button" className="booking-notification-open" onClick={() => { dismiss(row); onOpen?.() }}>Mở Live Tour</button>
  </aside></NotificationModal>
}
