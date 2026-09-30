import ManualOnlineBooking from './ManualOnlineBooking'
import { useEffect, useState } from 'react'
import EmployeeProfileModal from './EmployeeProfileModal'
import { RequestCard } from '../pages/OnlineBookingPage'
import { canViewOnlineBookings } from '../lib/onlineBookings'
import { veraApi } from '../lib/api'
import { formatVeraDate } from '../lib/veraDate'

export default function UpcomingOnlineBookings({ user, onClose, services = [] }) {
  const [creating, setCreating] = useState(false)
  const [selected, setSelected] = useState(null)
  const [page, setPage] = useState(1)
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState({ rows: [], total: 0 })
  const [busy, setBusy] = useState(true)
  const [error, setError] = useState('')
  const allowed = canViewOnlineBookings(user)
  const reload = () => setVersion(value => value + 1)
  useEffect(() => {
    if (!allowed) return undefined
    let active = true
    setBusy(true); setError('')
    veraApi.onlineBookings({ upcoming: true, page }).then(data => {
      if (!active) return
      if (!data.rows.length && page > 1) { setPage(value => value - 1); return }
      setResult(data)
    }).catch(err => { if (active) setError(err.message) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [allowed, page, version])
  if (!allowed) return null
  // Only one focus trap is mounted; returning from details restores the list.
  if (creating) return <ManualOnlineBooking services={services} onClose={() => setCreating(false)} onSaved={() => { setCreating(false); setPage(1); reload() }}/>
  if (selected) return <RequestCard key={`${selected.id}:${selected.revision}`} row={selected} services={services} reload={reload} onClose={() => setSelected(null)}/>
  return <EmployeeProfileModal labelledBy="upcoming-booking-title" className="upcoming-booking-modal" onClose={onClose}>
    <header>
      <h2 id="upcoming-booking-title">Booking online sắp tới</h2>
      <button onClick={onClose}>Đóng</button>
    </header>
    <div className="upcoming-booking-toolbar">
      <button aria-haspopup="dialog" onClick={() => setCreating(true)}>Thêm Lịch đặt Booking</button>
      <button disabled={busy} onClick={reload}>Làm mới</button>
    </div>
    {error && <p role="alert">{error}</p>}
    {busy ? <p role="status">Đang tải…</p> : !error && <>
      <p>{result.total} lịch hẹn</p>
      <div className="upcoming-booking-list">{result.rows.map(row => <article key={row.id}>
        <strong>#{row.id} · {row.customer_name}</strong>
        <span>{formatVeraDate(row.appointment_date)} · {row.appointment_time}</span>
        <span>{row.phone || 'Không cung cấp số điện thoại'} · {row.guests} khách</span><span>{row.service}</span>
        <span>{row.status === 'confirmed' ? 'Đã xác nhận' : 'Mới nhận'}</span>
        <button aria-haspopup="dialog" onClick={() => setSelected(row)}>Chi tiết</button>
      </article>)}</div>
      {!result.rows.length && <p>Không có lịch hẹn trong khoảng thời gian này.</p>}
    </>}
    <nav className="online-booking-actions" aria-label="Phân trang booking sắp tới">
      <button disabled={busy || page <= 1} onClick={() => setPage(value => value - 1)}>Trước</button>
      <span>Trang {page} / {Math.max(1, Math.ceil(result.total / 25))}</span>
      <button disabled={busy || page * 25 >= result.total} onClick={() => setPage(value => value + 1)}>Sau</button>
    </nav>
  </EmployeeProfileModal>
}
