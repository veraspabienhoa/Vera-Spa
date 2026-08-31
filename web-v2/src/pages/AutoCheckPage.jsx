import { useEffect, useState } from 'react'
import { Activity, Pause, Play, RefreshCw, ShieldCheck } from 'lucide-react'
import { veraApi } from '../lib/api'

export default function AutoCheckPage({ user }) {
  const [data, setData] = useState(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const load = async () => {
    setError('')
    try { setData(await veraApi.autoCheck()) } catch (err) { setError(err.message) }
  }
  useEffect(() => { load() }, [])
  const update = async (body) => {
    setBusy(true); setError('')
    try { await veraApi.updateAutoCheck(body); await load() } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const run = async () => {
    setBusy(true); setError('')
    try { const result = await veraApi.runAutoCheck(); await load(); window.alert(result.message) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  const cfg = data?.config || {}
  const connected = Boolean(data)
  const canControl = user?.role === 'admin' || user?.permissions?.auto_penalty_control
  const canRun = user?.role === 'admin' || user?.permissions?.auto_penalty_run
  return <section className="page-stack auto-check-page">
    <style>{`.auto-check-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:14px}.auto-check-card{background:#fff;border:1px solid #dfe8e2;border-radius:22px;padding:20px}.auto-check-card strong{display:block;font-size:27px;color:#14382c;margin-top:8px}.auto-check-actions{display:flex;gap:12px;flex-wrap:wrap}.auto-check-table{width:100%;border-collapse:collapse}.auto-check-table th,.auto-check-table td{padding:12px 9px;text-align:left;border-bottom:1px solid #e7ece9;font-size:14px}.auto-check-table th{color:#627169}.auto-check-ok{color:#17734b}.auto-check-paused{color:#a45d1a}@media(max-width:720px){.auto-check-grid{grid-template-columns:1fr}.auto-check-table th:nth-child(4),.auto-check-table td:nth-child(4){display:none}}`}</style>
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
    <div className="panel auto-check-card"><h2>Lịch sử ghi nhận gần nhất</h2><div className="table-scroll"><table className="auto-check-table"><thead><tr><th>Ngày</th><th>Nhân viên</th><th>Lý do</th><th>Nguồn</th><th>Phút</th></tr></thead><tbody>{(data?.events || []).map((row, i) => <tr key={`${row.created_at}-${i}`}><td>{row.work_date}</td><td><b>{row.employee_name}</b></td><td>{row.reason}</td><td>{row.source}</td><td>{row.minutes}</td></tr>)}{!data?.events?.length && <tr><td colSpan="5">Chưa có dữ liệu Auto Check trong PostgreSQL.</td></tr>}</tbody></table></div></div>
  </section>
}
