import './LeaveQuotaCheck.css'
import { ShieldAlert } from 'lucide-react'
import { useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDate } from '../lib/veraDate'

const labels = { days: 'Ngày nghỉ', weekends: 'Cuối tuần Nhóm 3', generated: 'Phát sinh' }
export default function LeaveQuotaCheck() {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const revision = useRef(0)
  const check = async () => {
    const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' }).formatToParts(new Date())
    const year = parts.find(p => p.type === 'year').value
    const month = parts.find(p => p.type === 'month').value
    const start = `${year}-${month}-01`
    const end = `${year}-${month}-${new Date(Date.UTC(Number(year), Number(month), 0)).getUTCDate()}`
    const current = ++revision.current
    setBusy(true); setError(''); setResult(null)
    try {
      const data = await veraApi.leaveQuotaCheck(start, end)
      if (revision.current === current) setResult(data)
    } catch (err) {
      if (revision.current === current) setError(err.message || 'Không kiểm tra được hạn mức.')
    } finally {
      if (revision.current === current) setBusy(false)
    }
  }
  return <div className="leave-list-personal-summary-note leave-quota-check">
    <button className="leave-quota-check-button" data-ui-key="u-67672e9aae74" type="button" disabled={busy} onClick={check}><ShieldAlert size={22} aria-hidden="true"/>{busy ? 'Đang kiểm tra…' : 'Kiểm tra vượt hạn mức · Tháng này'}</button>
    <div className="leave-quota-check-result" aria-live="polite" aria-busy={busy}>
      {error && <p role="alert">{error}</p>}
      {busy && <p>Đang kiểm tra hạn mức…</p>}
      {result && <><p>{formatVeraDate(result.start)} – {formatVeraDate(result.end)}: {result.items.length ? `${result.items.length} trường hợp nhân viên/tháng vượt hạn mức` : 'Không phát hiện trường hợp vượt hạn mức.'}</p>
      <div className="leave-quota-check-items">{result.items.map(item => <div className="leave-quota-check-item" key={`${item.employee}-${item.month}`}>
        <strong>{item.employee} · {item.month.split('-').reverse().join('/')}</strong>
        <div>{item.exceeded.map(key => `${labels[key]}: ${Number(item[key]).toLocaleString('vi-VN')}/${key === 'days' ? (item.day_limit ?? result.limits[key]) : result.limits[key]}`).join(' · ')}</div>
        {item.borrowed > 0 && <div>Nghỉ bệnh được duyệt: {Number(item.sick_days).toLocaleString('vi-VN')} ngày · Ứng thêm: {Number(item.borrowed).toLocaleString('vi-VN')} ngày (trừ phép tháng kế tiếp).</div>}
      </div>)}</div></>}
    </div>
  </div>
}
