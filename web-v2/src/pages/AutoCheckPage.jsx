import { useEffect, useState } from 'react'
import { Activity, Database, Pause, Play, RefreshCw, ShieldCheck } from 'lucide-react'
import { veraApi } from '../lib/api'
import { tourCacheControl } from '../lib/tourCacheControl'

const dateTimeText = (value) => {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? String(value) : date.toLocaleString('vi-VN')
}

export default function AutoCheckPage({ user }) {
  const [data, setData] = useState(null)
  const [tourControl, setTourControl] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [tourBusy, setTourBusy] = useState(false)
  const [tourMessage, setTourMessage] = useState('')
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'

  const loadTourControl = async () => {
    if (!isAdmin) return
    try { setTourControl(await tourCacheControl.get()) } catch (err) { setError(err.message) }
  }

  const load = async () => {
    setError('')
    try {
      setData(await veraApi.autoCheck())
      await loadTourControl()
    } catch (err) {
      setError(err.message)
    }
  }

  useEffect(() => { void load() }, [isAdmin])

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
      setTourMessage(result.message || (result.disabled ? 'Đã tạm dừng đồng bộ TourVera.' : 'Đã mở lại đồng bộ TourVera.'))
    } catch (err) {
      setError(err.message || 'Không thay đổi được trạng thái đồng bộ TourVera.')
    } finally {
      setTourBusy(false)
    }
  }

  const cfg = data?.config || {}
  const connected = Boolean(data)
  const canControl = isAdmin || user?.permissions?.auto_penalty_control
  const canRun = isAdmin || user?.permissions?.auto_penalty_run

  return <section className="page-stack auto-check-page">
    <style>{`.auto-check-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.auto-check-card{background:#fff;border:1px solid #dfe8e2;border-radius:22px;padding:20px}.auto-check-card strong{display:block;font-size:27px;color:#14382c;margin-top:8px}.auto-check-actions{display:flex;gap:12px;flex-wrap:wrap;align-items:center}.auto-check-table{width:100%;border-collapse:collapse}.auto-check-table th,.auto-check-table td{padding:12px 9px;text-align:left;border-bottom:1px solid #e7ece9;font-size:14px}.auto-check-table th{color:#627169}.auto-check-ok{color:#17734b}.auto-check-paused{color:#a45d1a}.tour-cache-control-card{border:2px solid #dfe8e2}.tour-cache-control-head{display:flex;justify-content:space-between;gap:16px;align-items:flex-start}.tour-cache-control-head h2{margin:0 0 5px}.tour-cache-control-status{font-weight:900;font-size:18px}.tour-cache-control-note{margin:12px 0;color:#52665e;line-height:1.55}.tour-cache-meta{display:flex;gap:18px;flex-wrap:wrap;font-size:12px;color:#66766f;margin-top:12px}.tour-cache-message{margin-top:12px}@media(max-width:720px){.auto-check-grid{grid-template-columns:1fr}.auto-check-table th:nth-child(4),.auto-check-table td:nth-child(4){display:none}.tour-cache-control-head{flex-direction:column}}`}</style>
    <div className="page-heading"><div><span className="eyebrow"><ShieldCheck size={18}/> VẬN HÀNH</span><h1>Auto Check</h1><p>Kiểm tra tự động từ TimeSoft và Bảng tua; dữ liệu được ghi trực tiếp vào PostgreSQL.</p></div><button className="secondary-button" onClick={load}><RefreshCw size={17}/> Làm mới</button></div>
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

    {isAdmin && <div className="panel auto-check-card tour-cache-control-card">
      <div className="tour-cache-control-head">
        <div>
          <span className="eyebrow"><Database size={17}/> GIẢM TẢI HỆ THỐNG</span>
          <h2>TourVera cho cảnh báo nghỉ giữa ca</h2>
          <div className={`tour-cache-control-status ${tourControl?.disabled ? 'auto-check-paused' : 'auto-check-ok'}`}>
            {!tourControl ? 'Đang kiểm tra…' : tourControl.disabled ? 'ĐÃ TẠM DỪNG' : 'ĐANG ĐỒNG BỘ'}
          </div>
        </div>
        <button
          className={tourControl?.disabled ? 'primary-button' : 'secondary-button'}
          disabled={tourBusy || !tourControl}
          onClick={toggleTourCache}
        >
          {tourControl?.disabled ? <Play size={17}/> : <Pause size={17}/>}
          {tourBusy ? 'Đang cập nhật…' : tourControl?.disabled ? 'Mở lại tải TourVera' : 'Tạm dừng tải TourVera'}
        </button>
      </div>
      <p className="tour-cache-control-note">
        Khi tạm dừng, job nền 5 phút sẽ không tải TourVera.xlsm chỉ để tạo cache cho Chấm công/cảnh báo nghỉ giữa ca. Web V2 cũng ngừng dùng cache TourVera ngay lập tức. Đồng bộ Chấm công TimeSoft vẫn chạy bình thường và Auto Check chuyên biệt không bị tắt.
      </p>
      <div className="tour-cache-meta">
        <span>Cache cập nhật gần nhất: <b>{dateTimeText(tourControl?.cache_updated_at)}</b></span>
        <span>Người thay đổi: <b>{tourControl?.updated_by || '—'}</b></span>
      </div>
      {tourMessage && <div className="success-box tour-cache-message">{tourMessage}</div>}
    </div>}

    <div className="panel auto-check-card"><h2>Lịch sử ghi nhận gần nhất</h2><div className="table-scroll"><table className="auto-check-table"><thead><tr><th>Ngày</th><th>Nhân viên</th><th>Lý do</th><th>Nguồn</th><th>Phút</th></tr></thead><tbody>{(data?.events || []).map((row, i) => <tr key={`${row.created_at}-${i}`}><td>{row.work_date}</td><td><b>{row.employee_name}</b></td><td>{row.reason}</td><td>{row.source}</td><td>{row.minutes}</td></tr>)}{!data?.events?.length && <tr><td colSpan="5">Chưa có dữ liệu Auto Check trong PostgreSQL.</td></tr>}</tbody></table></div></div>
  </section>
}
