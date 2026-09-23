import { useState } from 'react'
import { History, RefreshCw } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import { veraApi } from '../lib/api'
import { formatVeraDate } from '../lib/veraDate'

const today = () => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric',
  }).formatToParts(new Date()).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

export default function CheckinHistoryPage() {
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(today)
  const [search, setSearch] = useState('')
  const [records, setRecords] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async (event) => {
    event.preventDefault()
    if (!event.currentTarget.checkValidity() || !start || !end || start > end) return
    setBusy(true)
    setError('')
    try {
      const response = await veraApi.snapshot(start, end)
      setRecords(response.records || [])
    } catch (cause) {
      setError(cause.message || 'Không tải được lịch sử chấm công.')
      setRecords(null)
    } finally { setBusy(false) }
  }

  const visible = (records || []).filter(item =>
    `${item.employee_name || ''} ${item.employee_code || ''}`.toLocaleLowerCase('vi-VN').includes(search.trim().toLocaleLowerCase('vi-VN')))

  return <section className="checkin-history-page">
    <div className="page-heading"><div><span className="eyebrow"><History size={16} /> TIMESOFT FACEID</span><h1>LỊCH SỬ CHECKIN</h1><p>Các lần chấm công nhân viên đã đồng bộ vào hệ thống VERA.</p></div></div>
    <form className="attendance-date-custom" onSubmit={load}>
      <label>Từ ngày<VeraDateInput value={start} onChange={event => setStart(event.target.value)} required /></label>
      <label>Đến ngày<VeraDateInput value={end} min={start} onChange={event => setEnd(event.target.value)} required /></label>
      <button className="secondary-button" type="submit" disabled={busy || !start || !end || start > end}><RefreshCw size={16} className={busy ? 'spin' : ''} /> {busy ? 'Đang tải…' : 'Xem lịch sử'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {records && <>
      <label>Tìm nhân viên<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder="Tên hoặc mã nhân viên" /></label>
      <p>{visible.length} bản ghi trong kỳ đã chọn. Nguồn: TimeSoft đã đồng bộ; không phải log trực tiếp từ thiết bị.</p>
      <div className="responsive-data-table"><table><thead><tr><th>Ngày</th><th>Mã nhân viên</th><th>Nhân viên</th><th>Giờ vào</th><th>Các lần chấm</th><th>Giờ ra</th></tr></thead><tbody>
        {visible.map((item, index) => <tr key={`${item.date}-${item.employee_code}-${index}`}>
          <td data-label="Ngày">{formatVeraDate(item.date, '—')}</td><td data-label="Mã nhân viên">{item.employee_code || '—'}</td>
          <td data-label="Nhân viên">{item.employee_name || '—'}</td><td data-label="Giờ vào">{item.check_in || '—'}</td>
          <td data-label="Các lần chấm">{(item.punch_times || []).join(' · ') || '—'}</td><td data-label="Giờ ra">{item.check_out || '—'}</td>
        </tr>)}
      </tbody></table></div>
    </>}
  </section>
}
