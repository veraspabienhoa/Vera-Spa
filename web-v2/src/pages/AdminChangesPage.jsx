import { Activity, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

const formatTime = (value) => new Intl.DateTimeFormat('vi-VN', { dateStyle: 'short', timeStyle: 'medium', timeZone: 'Asia/Ho_Chi_Minh' }).format(new Date(value))
export default function AdminChangesPage() {
  const [days, setDays] = useState(7)
  const [data, setData] = useState({ changes: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async () => { setBusy(true); setError(''); try { setData(await veraApi.adminChanges(days)) } catch (e) { setError(e.message) } finally { setBusy(false) } }
  useEffect(() => { void load() }, [days]) // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><Activity size={14} /> Admin</span><h1>THAY ĐỔI HỆ THỐNG</h1><p>Nhật ký vận hành không chứa mật khẩu, khóa thông báo, số tiền lương hoặc doanh thu.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {error && <div className="error-box">{error}</div>}
    <section className="panel data-toolbar"><label>Khoảng xem<select value={days} onChange={(e) => setDays(Number(e.target.value))}><option value="1">24 giờ</option><option value="7">7 ngày</option><option value="14">14 ngày</option><option value="31">31 ngày</option></select></label><div className="audit-total">{data.changes.length} thay đổi</div></section>
    <section className="panel audit-list">{data.changes.map((item) => <article key={item.id}><span className={`audit-operation ${item.event_type}`}>{item.event_type}</span><div><strong>{item.dataset_key}</strong><p>{item.detail || 'Thay đổi dữ liệu'}</p></div><time>{formatTime(item.created_at)}</time></article>)}{!data.changes.length && <div className="setup-note">Không có thay đổi trong khoảng đã chọn.</div>}</section>
  </div>
}
