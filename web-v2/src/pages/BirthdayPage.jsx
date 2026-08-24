import { Cake, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

export default function BirthdayPage() {
  const currentMonth = new Date().getMonth() + 1
  const [month, setMonth] = useState(currentMonth)
  const [data, setData] = useState({ birthdays: [] })
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const load = async () => {
    setBusy(true); setError('')
    try { setData(await veraApi.birthdays(month)) } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  useEffect(() => { void load() }, [month]) // eslint-disable-line react-hooks/exhaustive-deps
  return <div className="feature-page">
    <div className="page-heading"><div><span className="eyebrow"><Cake size={14} /> Nhân sự</span><h1>SINH NHẬT</h1><p>Thông báo sinh nhật của nhân viên đang làm việc.</p></div><button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {error && <div className="error-box">{error}</div>}
    <section className="panel data-toolbar"><label>Tháng<select value={month} onChange={(event) => setMonth(Number(event.target.value))}>{Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>Tháng {index + 1}</option>)}</select></label><div className="audit-total">{data.birthdays.length} sinh nhật</div></section>
    <section className="birthday-grid">{data.birthdays.map((item) => <article className={`panel birthday-card ${item.is_today ? 'today' : ''}`} key={item.username}><div className="birthday-day">{String(item.day).padStart(2, '0')}</div><div><strong>{item.full_name}</strong><span>{item.username} · {item.birth_date}</span>{item.is_today && <em>Hôm nay</em>}</div></article>)}</section>
    {!data.birthdays.length && <div className="panel setup-note">Tháng {month} chưa có sinh nhật nhân viên.</div>}
  </div>
}
