import { useCallback, useEffect, useState } from 'react'
import { Activity, CalendarDays, Database, Download, Pause, Play, RefreshCw, ShieldCheck } from 'lucide-react'
import { veraApi } from '../lib/api'
import { tourCacheControl } from '../lib/tourCacheControl'
import VeraDateInput from '../components/VeraDateInput'

const FILTER_OPTIONS = ['Hôm qua', 'Hôm nay', 'Tuần trước', 'Tháng trước', 'Tùy chỉnh']

const formatDateInput = (value) => {
  const date = new Date(value)
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const addDays = (value, days) => {
  const date = new Date(value)
  date.setDate(date.getDate() + days)
  return date
}

const rangeForFilter = (filter) => {
  const now = new Date()
  if (filter === 'Hôm qua') {
    const yesterday = addDays(now, -1)
    return [formatDateInput(yesterday), formatDateInput(yesterday)]
  }
  if (filter === 'Tuần trước') {
    const thisMonday = addDays(now, -((now.getDay() + 6) % 7))
    const previousMonday = addDays(thisMonday, -7)
    return [formatDateInput(previousMonday), formatDateInput(addDays(previousMonday, 6))]
  }
  if (filter === 'Tháng trước') {
    return [
      formatDateInput(new Date(now.getFullYear(), now.getMonth() - 1, 1)),
      formatDateInput(new Date(now.getFullYear(), now.getMonth(), 0)),
    ]
  }
  return [formatDateInput(now), formatDateInput(now)]
}

const displayDate = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}/${month}/${year}` : value || '—'
}

const dateTimeText = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('vi-VN')
}

export default function AutoCheckPage({ user }) {
  const initialRange = rangeForFilter('Hôm nay')
  const [data, setData] = useState(null)
  const [tourControl, setTourControl] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [tourBusy, setTourBusy] = useState(false)
  const [tourMessage, setTourMessage] = useState('')
  const [timeFilter, setTimeFilter] = useState('Hôm nay')
  const [startDate, setStartDate] = useState(initialRange[0])
  const [endDate, setEndDate] = useState(initialRange[1])
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'

  const loadTourControl = useCallback(async () => {
    if (!isAdmin) return
    try { setTourControl(await tourCacheControl.get()) } catch (err) { setError(err.message) }
  }, [isAdmin])

  const load = useCallback(async () => {
    if (!startDate || !endDate || endDate < startDate) {
      setError('Vui lòng chọn khoảng thời gian hợp lệ.')
      return
    }
    setLoading(true)
    setError('')
    try {
      setData(await veraApi.autoCheck(startDate, endDate))
      await loadTourControl()
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }, [endDate, loadTourControl, startDate])

  useEffect(() => { void load() }, [load])

  const selectTimeFilter = (filter) => {
    setTimeFilter(filter)
    if (filter === 'Tùy chỉnh') return
    const [start, end] = rangeForFilter(filter)
    setStartDate(start)
    setEndDate(end)
  }

  const exportExcel = async () => {
    if (!startDate || !endDate || endDate < startDate) {
      setError('Vui lòng chọn khoảng thời gian hợp lệ trước khi xuất Excel.')
      return
    }
    setExporting(true); setError('')
    try { await veraApi.exportAutoCheckExcel(startDate, endDate) }
    catch (err) { setError(err.message) }
    finally { setExporting(false) }
  }

  const update = async (body) => {
    setBusy(true); setError('')
    try { await veraApi.updateAutoCheck(body); await load() } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const run = async () => {
    setBusy(true); setError('')
    try { const result = await veraApi.runAutoCheck(); await load(); window.alert(result.message) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }

  const toggleTourCache = async () => {
    if (!isAdmin || !tourControl || tourBusy) return
    setTourBusy(true); setError(''); setTourMessage('')
    try {
      const result = await tourCacheControl.setDisabled(!tourControl.disabled)
      setTourControl(result)
      setTourMessage(result.message || (result.disabled ? 'Đã tạm dừng làm mới TourVera.' : 'Đã mở lại làm mới TourVera.'))
    } catch (err) {
      setError(err.message || 'Không thay đổi được trạng thái làm mới TourVera.')
    } finally {
      setTourBusy(false)
    }
  }

  const cfg = data?.config || {}
  const connected = Boolean(data)
  const canControl = isAdmin || user?.permissions?.auto_penalty_control
  const canRun = isAdmin || user?.permissions?.auto_penalty_run

  return <section className="page-stack auto-check-page">
    <style>{`.auto-check-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.auto-check-card{background:#fff;border:1px solid #dfe8e2;border-radius:22px;padding:20px}.auto-check-card strong{display:block;font-size:27px;color:#14382c;margin-top:8px}.auto-check-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.auto-check-filter{display:flex;gap:10px;flex-wrap:wrap;align-items:center}.auto-check-filter button.active{background:#1f513f;color:#fff;border-color:#1f513f}.auto-check-custom{display:flex;gap:10px;align-items:flex-end;flex-wrap:wrap;margin-top:14px}.auto-check-custom label{display:flex;flex-direction:column;gap:5px;font-size:12px;color:#627169}.auto-check-custom input{min-width:165px}.auto-check-history-head{display:flex;justify-content:space-between;gap:16px;align-items:center;margin-bottom:12px}.auto-check-history-head h2{margin:0}.auto-check-period{font-size:13px;color:#627169}.auto-check-table{width:100%;border-collapse:collapse}.auto-check-table th,.auto-check-table td{padding:12px 9px;text-align:left;border-bottom:1px solid #e7ece9;font-size:14px}.auto-check-table th{color:#627169}.auto-check-ok{color:#17734b}.auto-check-paused{color:#a45d1a}.tour-cache-control-card{border:2px solid #dfe8e2}.tour-cache-control-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.tour-cache-control-head h2{margin:0 0 5px}.tour-cache-control-status{font-weight:900;font-size:18px}.tour-cache-control-note{margin:12px 0;color:#52665e;line-height:1.55}.tour-cache-meta{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#66766f;margin-top:12px}.tour-cache-message{margin-top:12px}@media(max-width:720px){.auto-check-grid{grid-template-columns:1fr}.auto-check-table th:nth-child(4),.auto-check-table td:nth-child(4){display:none}.tour-cache-control-head,.auto-check-history-head{align-items:stretch;flex-direction:column}.auto-check-history-head button{width:100%}.auto-check-custom label{flex:1}.auto-check-custom input{min-width:0;width:100%}}`}</style>
    <div className="page-heading"><div><span className="eyebrow"><ShieldCheck size={18}/> VẬN HÀNH</span><h1>Auto Check</h1><p>Kiểm tra tự động từ TimeSoft và Bảng tua; dữ liệu được ghi trực tiếp vào PostgreSQL.</p></div><button className="secondary-button" onClick={load} disabled={loading}><RefreshCw size={17} className={loading ? 'spin' : ''}/> {loading ? 'Đang tải…' : 'Làm mới'}</button></div>
    {error && <div className="error-box">{error}</div>}
    <div className="auto-check-grid">
      <div className="auto-check-card"><span>Trạng thái</span><strong className={connected && cfg.status !== 'PAUSED' ? 'auto-check-ok' : 'auto-check-paused'}>{!connected ? 'Chưa kết nối' : cfg.status === 'PAUSED' ? 'Tạm dừng' : 'Đang chạy'}</strong></div>
      <div className="auto-check-card"><span>Ngưỡng ghi nhận</span><strong>{connected ? `${cfg.threshold_minutes || 5} phút` : '—'}</strong></div>
      <div className="auto-check-card"><span>Lịch kiểm tra chuẩn</span><strong>{connected ? (cfg.schedule_hours || [15,20,21]).map(x => `${x}:00`).join(' · ') : '—'}</strong></div>
    </div>
    <div className="panel auto-check-card"><h2>Điều khiển</h2><div className="auto-check-actions">
      {canControl && <button className="secondary-button" disabled={busy || !connected} onClick={() => update({status: cfg.status === 'PAUSED' ? 'RUNNING' : 'PAUSED'})}>{cfg.status === 'PAUSED' ? <Play size={17}/> : <Pause size={17}/>} {cfg.status === 'PAUSED' ? 'Mở Auto Check' : 'Tạm dừng'}</button>}
      {canRun && <button className="primary-button" disabled={busy || !connected || cfg.status === 'PAUSED'} onClick={run}><Activity size={17}/> Chạy Auto Check</button>}
    </div></div>

    <div className="panel auto-check-card">
      <span className="eyebrow"><CalendarDays size={17}/> LỌC LỊCH SỬ</span>
      <div className="auto-check-filter">
        {FILTER_OPTIONS.map((filter) => <button key={filter} type="button" className={`secondary-button${timeFilter === filter ? ' active' : ''}`} onClick={() => selectTimeFilter(filter)}>{filter}</button>)}
      </div>
      {timeFilter === 'Tùy chỉnh' && <div className="auto-check-custom">
        <label>Từ ngày<VeraDateInput aria-label="Từ ngày" value={startDate} onChange={(event) => setStartDate(event.target.value)} /></label>
        <label>Đến ngày<VeraDateInput aria-label="Đến ngày" value={endDate} onChange={(event) => setEndDate(event.target.value)} /></label>
      </div>}
    </div>

    {isAdmin && <div className="panel auto-check-card tour-cache-control-card">
      <div className="tour-cache-control-head">
        <div>
          <span className="eyebrow"><Database size={17}/> GIẢM TẢI HỆ THỐNG</span>
          <h2>TourVera cho cảnh báo nghỉ giữa ca</h2>
          <div className={`tour-cache-control-status ${tourControl?.disabled ? 'auto-check-paused' : 'auto-check-ok'}`}>
            {!tourControl ? 'Đang kiểm tra…' : tourControl.disabled ? 'ĐÃ TẠM DỪNG LÀM MỚI' : 'ĐANG LÀM MỚI ĐỊNH KỲ'}
          </div>
        </div>
        <button
          className={tourControl?.disabled ? 'primary-button' : 'secondary-button'}
          disabled={tourBusy || !tourControl}
          onClick={toggleTourCache}
        >
          {tourControl?.disabled ? <Play size={17}/> : <Pause size={17}/>}
          {tourBusy ? 'Đang cập nhật…' : tourControl?.disabled ? 'Mở lại làm mới TourVera' : 'Tạm dừng làm mới TourVera'}
        </button>
      </div>
      <p className="tour-cache-control-note">
        Nút này chỉ tạm dừng lượt tải TourVera.xlsm định kỳ dùng riêng để làm mới cache, không tắt cảnh báo nghỉ giữa ca. Quản lý, Lễ tân và Nhân viên vẫn nhận cảnh báo bình thường: TimeSoft là nguồn chính; cache TourVera của cùng ngày tiếp tục được dùng làm fallback. Nếu Auto Check đã cần tải TourVera cho công việc riêng thì dữ liệu đã tải có thể cập nhật cache mà không phát sinh thêm lượt tải Google Drive.
      </p>
      <div className="tour-cache-meta">
        <span>Cảnh báo nghỉ giữa ca: <b className="auto-check-ok">ĐANG HOẠT ĐỘNG</b></span>
        <span>Cache cập nhật gần nhất: <b>{dateTimeText(tourControl?.cache_updated_at)}</b></span>
        <span>Người thay đổi: <b>{tourControl?.updated_by || '—'}</b></span>
      </div>
      {tourMessage && <div className="success-box tour-cache-message">{tourMessage}</div>}
    </div>}

    <div className="panel auto-check-card"><div className="auto-check-history-head"><div><h2>Lịch sử ghi nhận</h2><div className="auto-check-period">{displayDate(startDate)} – {displayDate(endDate)} · {(data?.events || []).length} dòng</div></div><button className="secondary-button" onClick={exportExcel} disabled={exporting || loading}><Download size={17}/> {exporting ? 'Đang xuất…' : 'Export Excel'}</button></div><div className="table-scroll"><table className="auto-check-table"><thead><tr><th>Ngày</th><th>Nhân viên</th><th>Lý do</th><th>Nguồn</th><th>Phút</th></tr></thead><tbody>{(data?.events || []).map((row, i) => <tr key={`${row.created_at}-${i}`}><td>{displayDate(row.work_date)}</td><td><b>{row.employee_name}</b></td><td>{row.reason}</td><td>{row.source}</td><td>{row.minutes}</td></tr>)}{!data?.events?.length && <tr><td colSpan="5">Không có dữ liệu Auto Check trong khoảng thời gian đã chọn.</td></tr>}</tbody></table></div></div>
  </section>
}
