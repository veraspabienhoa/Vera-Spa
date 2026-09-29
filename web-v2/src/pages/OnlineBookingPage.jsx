import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDateTime } from '../lib/veraDate'
import OnlineBookingDetails from '../components/OnlineBookingDetails'
import { canViewOnlineBookings } from '../lib/onlineBookings'
import './OnlineBookingPage.css'

const statuses = { new: 'Mới nhận', confirmed: 'Đã xác nhận', handled: 'Đã xử lý', cancelled: 'Đã hủy' }
function RequestCard({ row, reload }) {
  const [status, setStatus] = useState(row.status)
  const [note, setNote] = useState(row.note)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const save = async () => {
    setBusy(true); setError('')
    try {
      await veraApi.updateOnlineBooking(row.id, { status, note, revision: row.revision })
      window.dispatchEvent(new Event('vera-online-bookings-changed'))
      reload()
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <article className="online-booking-card">
    <header><strong>#{row.id} · {row.kind === 'booking' ? 'Đặt lịch' : 'Liên hệ'}</strong><span>{formatVeraDateTime(row.created_at)}</span></header>
    <OnlineBookingDetails row={row}/>
    <div className="online-booking-actions"><label>Trạng thái<select value={status} onChange={e => setStatus(e.target.value)}>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label></div>
    <label>Ghi chú xử lý<textarea value={note} maxLength={2000} onChange={e => setNote(e.target.value)}/></label>
    {row.updated_by && <small>Cập nhật: {row.updated_by} · {formatVeraDateTime(row.updated_at)}</small>}
    {error && <p role="alert">{error}</p>}
    <button disabled={busy || (status === row.status && note === row.note)} onClick={save}>{busy ? 'Đang lưu…' : 'Lưu'}</button>
  </article>
}

export default function OnlineBookingPage({ user }) {
  const [page, setPage] = useState(1)
  const [status, setStatus] = useState('')
  const [kind, setKind] = useState('')
  const [search, setSearch] = useState('')
  const [q, setQ] = useState('')
  const [version, setVersion] = useState(0)
  const [result, setResult] = useState({ rows: [], total: 0 })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const allowed = canViewOnlineBookings(user)
  const reload = () => setVersion(v => v + 1)
  useEffect(() => {
    if (!allowed) return undefined
    let active = true
    setBusy(true); setError('')
    veraApi.onlineBookings({ page, status, kind, q }).then(data => { if (active) setResult(data) }).catch(err => { if (active) setError(err.message) }).finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [allowed, page, status, kind, q, version])
  if (!allowed) return <p role="alert">Chỉ Admin, Quản lý và Lễ tân được xem Booking online.</p>
  return <section className="online-booking-page">
    <h1>Booking online</h1><p>Yêu cầu đặt lịch và lời nhắn từ website. Lễ tân xác nhận với khách trước khi xếp phòng và nhân viên trên Live Tour.</p>
    <form className="online-booking-actions" onSubmit={e => { e.preventDefault(); setPage(1); setQ(search.trim()); reload() }}>
      <input aria-label="Tìm tên hoặc số điện thoại" placeholder="Tên hoặc số điện thoại" value={search} onChange={e => setSearch(e.target.value)} maxLength={100}/><button>Tìm</button>
      <select aria-label="Trạng thái" value={status} onChange={e => { setPage(1); setStatus(e.target.value) }}><option value="">Tất cả trạng thái</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select>
      <select aria-label="Loại yêu cầu" value={kind} onChange={e => { setPage(1); setKind(e.target.value) }}><option value="">Đặt lịch và liên hệ</option><option value="booking">Đặt lịch</option><option value="contact">Liên hệ</option></select>
      <button type="button" disabled={busy} onClick={reload}>Làm mới</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {busy ? <p role="status">Đang tải…</p> : <><p>{result.total} yêu cầu</p><div className="online-booking-grid">{result.rows.map(row => <RequestCard key={`${row.id}:${row.revision}`} row={row} reload={reload}/>)}</div>{!result.rows.length && <p>Không có yêu cầu phù hợp.</p>}</>}
    <nav className="online-booking-actions" aria-label="Phân trang booking"><button disabled={busy || page <= 1} onClick={() => setPage(p => p-1)}>Trước</button><span>Trang {page} / {Math.max(1, Math.ceil(result.total / 25))}</span><button disabled={busy || page * 25 >= result.total} onClick={() => setPage(p => p+1)}>Sau</button></nav>
  </section>
}
