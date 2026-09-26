import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiCustomText from '../components/UiCustomText'
import { Cake, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

export default function BirthdayPage() {
  usePageRefresh(() => load(), () => Boolean(busy))
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
    <div data-ui-key="u-fb9da428c2f8" className="page-heading"><div><span className="eyebrow"><Cake size={14} /> Nhân sự</span><h1>SINH NHẬT</h1><p>Thông báo sinh nhật của nhân viên đang làm việc.</p></div><button data-ui-key="u-f77ad50eb5d8" data-ui-label-default="Làm mới" className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /><UiCustomText uiKey="u-f77ad50eb5d8"> Làm mới</UiCustomText></button></div>
    <StableFeedback>{error && <div className="error-box">{error}</div>}</StableFeedback>
    <section data-ui-key="u-f673b62f8b64" className="panel data-toolbar"><label>Tháng<select value={month} onChange={(event) => setMonth(Number(event.target.value))}>{Array.from({ length: 12 }, (_, index) => <option key={index + 1} value={index + 1}>Tháng {index + 1}</option>)}</select></label><div className="audit-total">{data.birthdays.length} sinh nhật</div></section>
    <section data-ui-key="u-6a73f127e80e" className="birthday-grid">{data.birthdays.map((item) => <article className={`panel birthday-card ${item.is_today ? 'today' : ''}`} key={item.username}><div className="birthday-day">{String(item.day).padStart(2, '0')}</div><div><strong>{item.full_name}</strong><span>{item.username} · {item.birth_date}</span>{item.is_today && <em>Hôm nay</em>}</div></article>)}</section>
    {!data.birthdays.length && <div data-ui-key="u-127e12a8a760" className="panel setup-note">Tháng {month} chưa có sinh nhật nhân viên.</div>}
  </div>
}
