import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import OnlineBookingDetails from './OnlineBookingDetails'
import '../pages/OnlineBookingPage.css'

import { canViewOnlineBookings } from '../lib/onlineBookings'

export default function OnlineBookingPopup({ user, onOpen }) {
  const seen = useRef(new Set())
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const allowed = canViewOnlineBookings(user)
  const account = user?.id || user?.username || user?.employee_username
  useEffect(() => {
    setRows([])
    seen.current = new Set()
    if (!allowed) return undefined
    let active = true
    let pending = false
    let sequence = 0
    const load = async () => {
      if (pending || document.hidden) return
      pending = true
      const version = ++sequence
      try {
        const result = await veraApi.onlineBookingsUnread()
        if (active && version === sequence) setRows((result.rows || []).filter(row => !seen.current.has(row.id)))
      } catch { /* Retry after reconnect; never block Live Tour. */ }
      finally { pending = false }
    }
    const changed = () => { sequence += 1; setRows([]); void load() }
    void load()
    const timer = window.setInterval(load, 5000)
    document.addEventListener('visibilitychange', load)
    window.addEventListener('vera-online-bookings-changed', changed)
    return () => { active = false; window.clearInterval(timer); document.removeEventListener('visibilitychange', load); window.removeEventListener('vera-online-bookings-changed', changed) }
  }, [allowed, account])
  if (!allowed || !rows.length) return null
  const row = rows[0]
  const dismiss = async (open = false) => {
    setBusy(true); setError('')
    try {
      await veraApi.onlineBookingSeen(row.id)
      seen.current.add(row.id)
      setRows(current => current.filter(item => item.id !== row.id))
      if (open) onOpen()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <aside className="online-booking-popup" role="region" aria-label="Yêu cầu từ website">
    <strong aria-live="polite">{row.kind === 'booking' ? 'Booking online mới' : 'Lời nhắn mới'}{rows.length > 1 ? ` · ${rows.length} chờ xem` : ''}</strong>
    <OnlineBookingDetails row={row}/>
    {error && <p role="alert">{error}</p>}
    <div className="online-booking-actions"><button disabled={busy} onClick={() => dismiss()}>Đã xem</button><button disabled={busy} onClick={() => dismiss(true)}>Mở Booking online</button></div>
  </aside>
}
