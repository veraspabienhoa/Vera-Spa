import { useEffect, useState } from 'react'
import { History, RefreshCw } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import { veraApi } from '../lib/api'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'

const today = () => {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric',
  }).formatToParts(new Date()).map(part => [part.type, part.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

function CaptureImageButton({ record }) {
  const [imageUrl, setImageUrl] = useState('')
  const [open, setOpen] = useState(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  useEffect(() => () => { if (imageUrl) URL.revokeObjectURL(imageUrl) }, [imageUrl])

  const toggle = async () => {
    if (imageUrl) { setOpen(value => !value); return }
    setBusy(true); setError('')
    try {
      const blob = await veraApi.facegateCaptureImage(record.image_ref)
      if (!String(blob.type || '').toLowerCase().startsWith('image/')) throw new Error('Thiết bị không trả về dữ liệu ảnh.')
      setImageUrl(URL.createObjectURL(blob)); setOpen(true)
    } catch (cause) {
      setError(cause.message || 'Không tải được ảnh capture.')
    } finally { setBusy(false) }
  }

  return <div>
    <button className="secondary-button" type="button" disabled={busy} onClick={toggle}>{busy ? 'Đang tải ảnh…' : open ? 'Ẩn ảnh' : 'Xem ảnh'}</button>
    {error && <small role="alert">{error}</small>}
    {open && imageUrl && <div><img src={imageUrl} alt={`Ảnh capture sự kiện ${record.event_id}`} loading="lazy" style={{ display: 'block', width: 120, height: 160, objectFit: 'contain', marginTop: 8 }} /></div>}
  </div>
}

export default function CheckinHistoryPage() {
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(today)
  const [search, setSearch] = useState('')
  const [source, setSource] = useState('facegate')
  const [records, setRecords] = useState(null)
  const [truncated, setTruncated] = useState(false)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const load = async (event) => {
    event.preventDefault()
    if (!event.currentTarget.checkValidity() || !start || !end || start > end) return
    setBusy(true)
    setError('')
    setTruncated(false)
    try {
      const response = source === 'facegate'
        ? await veraApi.facegateControlLog(start, end)
        : source === 'capture'
          ? await veraApi.facegateCaptureLog(start, end)
          : await veraApi.snapshot(start, end)
      setRecords(response.records || [])
      setTruncated(Boolean(response.truncated))
    } catch (cause) {
      setError(cause.message || 'Không tải được lịch sử chấm công.')
      setRecords(null)
    } finally { setBusy(false) }
  }

  const visible = (records || []).filter(item =>
    `${item.employee_name || item.device_name || item.event_text || ''} ${item.employee_code || ''} ${item.event_id || ''}`.toLocaleLowerCase('vi-VN').includes(search.trim().toLocaleLowerCase('vi-VN')))

  return <section className="checkin-history-page">
    <div className="page-heading"><div><span className="eyebrow"><History size={16} /> FACE ID · CHẤM CÔNG</span><h1>LỊCH SỬ CHECKIN</h1><p>Tra cứu nhật ký thiết bị hoặc dữ liệu chấm công đã đồng bộ vào VERA.</p></div></div>
    <form className="attendance-date-custom" onSubmit={load}>
      <label>Nguồn dữ liệu<select value={source} onChange={event => { setSource(event.target.value); setRecords(null); setError('') }}><option value="facegate">FaceGate · Control Log</option><option value="capture">FaceGate · Capture Log</option><option value="timesoft">TimeSoft · Đã đồng bộ VERA</option></select></label>
      <label>Từ ngày<VeraDateInput value={start} onChange={event => setStart(event.target.value)} required /></label>
      <label>Đến ngày<VeraDateInput value={end} min={start} onChange={event => setEnd(event.target.value)} required /></label>
      <button className="secondary-button" type="submit" disabled={busy || !start || !end || start > end}><RefreshCw size={16} className={busy ? 'spin' : ''} /> {busy ? 'Đang tải…' : 'Xem lịch sử'}</button>
    </form>
    {error && <p role="alert">{error}</p>}
    {records && <>
      <label>Tìm nhân viên<input type="search" value={search} onChange={event => setSearch(event.target.value)} placeholder={source === 'facegate' ? 'Tên trên máy hoặc mã sự kiện' : 'Tên hoặc mã nhân viên'} /></label>
      {source === 'facegate' ? <>
        <p>{visible.length} sự kiện FaceGate trong kỳ đã chọn. Trạng thái trên máy chưa được diễn giải; dữ liệu này chỉ để tra cứu, chưa ghép mã nhân viên và không dùng tính công/lương.</p>
        {truncated && <p role="status">Kết quả đã chạm giới hạn truy vấn; hãy thu hẹp khoảng ngày.</p>}
        <div className="responsive-data-table"><table><thead><tr><th>Mã sự kiện</th><th>Thời điểm</th><th>Tên hiển thị trên máy</th><th>Mã trạng thái</th></tr></thead><tbody>
          {visible.map(item => <tr key={item.event_id}>
            <td data-label="Mã sự kiện">{item.event_id}</td><td data-label="Thời điểm">{formatVeraDateTime(item.occurred_at, '—')}</td>
            <td data-label="Tên hiển thị trên máy">{item.device_name || '—'}</td><td data-label="Mã trạng thái">{item.status_code || '—'}</td>
          </tr>)}
        </tbody></table></div>
      </> : source === 'capture' ? <>
        <p>{visible.length} ảnh/sự kiện Capture Log trong kỳ. Máy không gửi mã nhân viên trong danh sách này; ảnh chỉ để Admin tra cứu, không ghép hồ sơ và không dùng tính công/lương. Ảnh chỉ tải khi bấm Xem ảnh và không lưu vào VERA.</p>
        {truncated && <p role="status">Kết quả đã chạm giới hạn truy vấn; hãy thu hẹp khoảng ngày.</p>}
        <div className="responsive-data-table"><table><thead><tr><th>Mã sự kiện</th><th>Thời điểm</th><th>Loại sự kiện</th><th>Trạng thái trên máy</th><th>Ảnh capture</th></tr></thead><tbody>
          {visible.map(item => <tr key={item.event_id}>
            <td data-label="Mã sự kiện">{item.event_id}</td><td data-label="Thời điểm">{formatVeraDateTime(item.occurred_at, '—')}</td>
            <td data-label="Loại sự kiện">{item.event_text || '—'}</td><td data-label="Trạng thái trên máy">{item.event_status || '—'}</td>
            <td data-label="Ảnh capture">{item.image_available ? <CaptureImageButton record={item} /> : 'Không có ảnh'}</td>
          </tr>)}
        </tbody></table></div>
      </> : <>
        <p>{visible.length} bản ghi trong kỳ đã chọn. Nguồn: TimeSoft đã đồng bộ; không phải log trực tiếp từ thiết bị.</p>
        <div className="responsive-data-table"><table><thead><tr><th>Ngày</th><th>Mã nhân viên</th><th>Nhân viên</th><th>Giờ vào</th><th>Các lần chấm</th><th>Giờ ra</th></tr></thead><tbody>
          {visible.map((item, index) => <tr key={`${item.date}-${item.employee_code}-${index}`}>
            <td data-label="Ngày">{formatVeraDate(item.date, '—')}</td><td data-label="Mã nhân viên">{item.employee_code || '—'}</td>
            <td data-label="Nhân viên">{item.employee_name || '—'}</td><td data-label="Giờ vào">{item.check_in || '—'}</td>
            <td data-label="Các lần chấm">{(item.punch_times || []).join(' · ') || '—'}</td><td data-label="Giờ ra">{item.check_out || '—'}</td>
          </tr>)}
        </tbody></table></div>
      </>}
    </>}
  </section>
}
