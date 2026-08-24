import { CalendarDays, Download, RefreshCw, ScanLine } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

const today = () => new Date().toISOString().slice(0, 10)
export default function SnapshotPage({ user }) {
  const [start, setStart] = useState(today())
  const [end, setEnd] = useState(today())
  const [records, setRecords] = useState([])
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async () => { setBusy(true); setError(''); try { const result = await veraApi.snapshot(start, end); setRecords(result.records || []) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><ScanLine size={14} /> Chấm công</span><h1>SNAPSHOT</h1><p>Dữ liệu chấm công nhân viên đã đồng bộ vào PostgreSQL. Trang này không hiển thị doanh thu.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {error && <div className="error-box">{error}</div>}
    <section className="panel data-toolbar"><label><CalendarDays size={15} /> Từ ngày<input type="date" value={start} onChange={(e) => setStart(e.target.value)} /></label><label><CalendarDays size={15} /> Đến ngày<input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)} /></label><button className="primary-button" onClick={load}>Xem dữ liệu</button>{user?.permissions?.snapshot_export && <button className="secondary-button" onClick={() => veraApi.exportSnapshotExcel(start, end)}><Download size={16} /> Export Excel</button>}</section>
    <section className="panel"><div className="panel-title-row"><div><h2>CHẤM CÔNG NHÂN VIÊN</h2><p>{records.length} bản ghi trong khoảng đã chọn.</p></div></div><div className="responsive-data-table"><table><thead><tr><th>Ngày</th><th>Nhân viên</th><th>Ca</th><th>Giờ vào</th><th>Giờ ra</th><th>Trạng thái</th><th>Trễ</th><th>Về sớm</th></tr></thead><tbody>{records.map((item, index) => <tr key={`${item.date}-${item.employee_code}-${item.check_in}-${index}`}><td>{item.date}</td><td><strong>{item.employee_name}</strong><small>{item.employee_code}</small></td><td>{item.shift}<small>{item.shift_start} – {item.shift_end}</small></td><td>{item.check_in || '—'}</td><td>{item.check_out || '—'}</td><td>{item.arrival_status}<small>{item.departure_status}</small></td><td>{item.late_minutes} phút</td><td>{item.early_minutes} phút</td></tr>)}</tbody></table></div>{!records.length && <div className="setup-note">Chưa có dữ liệu chấm công trong khoảng này.</div>}</section>
  </div>
}
