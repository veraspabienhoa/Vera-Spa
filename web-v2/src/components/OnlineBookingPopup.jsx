import { useEffect, useRef, useState } from 'react'
import { clampPopupPosition } from '../lib/popupPosition'
import { veraApi } from '../lib/api'
import OnlineBookingDetails from './OnlineBookingDetails'
import UpcomingOnlineBookings from './UpcomingOnlineBookings'
import { startQuarterHourBookingReminder } from '../lib/quarterHourBookingReminder'
import '../pages/OnlineBookingPage.css'

import { canViewOnlineBookings } from '../lib/onlineBookings'

export default function OnlineBookingPopup({ user, onOpen }) {
  const panel = useRef(null)
  const drag = useRef(null)
  const [position, setPosition] = useState(null)
  const [hidden, setHidden] = useState(false)
  const seen = useRef(new Set())
  const [rows, setRows] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [showUpcomingReminder, setShowUpcomingReminder] = useState(false)
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
  useEffect(() => {
    if (!allowed) return undefined
    return startQuarterHourBookingReminder({
      load: () => veraApi.onlineBookings({ upcoming: true, page: 1, limit: 1 }),
      onReminder: result => { if (result.total > 0) setShowUpcomingReminder(true) },
    })
  }, [allowed, account])
  const moveTo = next => {
    if (!panel.current) return
    const rect = panel.current.getBoundingClientRect()
    setPosition(clampPopupPosition(next, rect, { width: window.innerWidth, height: window.innerHeight }))
  }
  useEffect(() => {
    const constrain = () => {
      if (!panel.current) return
      const rect = panel.current.getBoundingClientRect()
      setPosition(current => current && clampPopupPosition(current, rect, { width: window.innerWidth, height: window.innerHeight }))
    }
    constrain()
    window.addEventListener('resize', constrain)
    return () => window.removeEventListener('resize', constrain)
  }, [hidden, rows.length])
  const beginDrag = event => {
    if (event.button !== 0) return
    const rect = panel.current.getBoundingClientRect()
    drag.current = { x: event.clientX, y: event.clientY, left: rect.left, top: rect.top }
    event.currentTarget.setPointerCapture(event.pointerId)
  }
  const moveDrag = event => {
    const start = drag.current
    if (start) moveTo({ left: start.left + event.clientX - start.x, top: start.top + event.clientY - start.y })
  }
  const keyboardMove = event => {
    const delta = { ArrowLeft: [-1, 0], ArrowRight: [1, 0], ArrowUp: [0, -1], ArrowDown: [0, 1] }[event.key]
    if (!delta) return
    event.preventDefault()
    const rect = panel.current.getBoundingClientRect()
    const step = event.shiftKey ? 30 : 10
    moveTo({ left: rect.left + delta[0] * step, top: rect.top + delta[1] * step })
  }
  if (!allowed) return null
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
  return <>{showUpcomingReminder && <UpcomingOnlineBookings user={user} onClose={() => setShowUpcomingReminder(false)}/>}
  {!rows.length || showUpcomingReminder ? null : <aside ref={panel} className={`online-booking-popup${hidden ? ' is-minimized' : ''}`} style={position ? { left: position.left, top: position.top, right: 'auto' } : undefined} role="region" aria-label="Yêu cầu từ website">
    <div className="online-booking-popup-header">
      <button type="button" className="online-booking-drag-handle" aria-label="Di chuyển thông báo bằng kéo hoặc phím mũi tên" onPointerDown={beginDrag} onPointerMove={moveDrag} onPointerUp={() => { drag.current = null }} onPointerCancel={() => { drag.current = null }} onLostPointerCapture={() => { drag.current = null }} onKeyDown={keyboardMove}>
        <strong aria-live="polite">{row.kind === 'booking' ? 'Booking online mới' : 'Lời nhắn mới'}{rows.length > 1 ? ` · ${rows.length}` : ''}</strong>
      </button>
      <button type="button" aria-expanded={!hidden} onClick={() => setHidden(value => !value)}>{hidden ? 'Hiện' : 'Ẩn'}</button>
      <button type="button" aria-label="Đóng thông báo booking online" disabled={busy} onClick={() => dismiss()}>Đóng</button>
    </div>
    {!hidden && <>
      <OnlineBookingDetails row={row}/>
      <div className="online-booking-actions"><button disabled={busy} onClick={() => dismiss()}>Đã xem</button><button disabled={busy} onClick={() => dismiss(true)}>Mở Booking online</button></div>
    </>}
    {error && <p role="alert">{error}</p>}
  </aside>}
  </>
}
