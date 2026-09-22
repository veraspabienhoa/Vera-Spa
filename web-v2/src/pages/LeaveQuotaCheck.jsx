import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { formatVeraDate } from '../lib/veraDate'

const labels = { days: 'Ngày nghỉ', weekends: 'Cuối tuần Nhóm 3', generated: 'Phát sinh' }
export default function LeaveQuotaCheck({ start, end }) {
  const [result, setResult] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const revision = useRef(0)
  useEffect(() => {
    revision.current += 1
    setResult(null); setError(''); setBusy(false)
    return () => { revision.current += 1 }
  }, [start, end])
  const check = async () => {
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
  return <div className="leave-list-personal-summary-note">
    <button type="button" disabled={busy || !start || !end} onClick={check}>{busy ? 'Đang kiểm tra…' : 'Kiểm tra vượt hạn mức'}</button>
    <p>Kiểm tra tất cả nhân viên, trọn từng tháng trong khoảng ngày đang chọn. Ngày nghỉ tính đúng 0,5 ngày; cuối tuần đếm ngày Thứ Bảy/Chủ Nhật thuộc Nhóm 3; phát sinh đếm số bản ghi.</p>
    {error && <p role="alert">{error}</p>}
    {result && <div aria-live="polite">
      <p>{formatVeraDate(result.start)} – {formatVeraDate(result.end)}: {result.items.length ? `${result.items.length} trường hợp nhân viên/tháng vượt hạn mức` : 'Không phát hiện trường hợp vượt hạn mức.'}</p>
      {result.items.map(item => <div key={`${item.employee}-${item.month}`} style={{ border: '1px solid #b45309', borderRadius: 8, padding: 8, marginTop: 8, background: '#fffbeb', overflowWrap: 'anywhere' }}>
        <strong>{item.employee} · {item.month.split('-').reverse().join('/')}</strong>
        <div>{item.exceeded.map(key => `${labels[key]}: ${Number(item[key]).toLocaleString('vi-VN')}/${key === 'days' ? (item.day_limit ?? result.limits[key]) : result.limits[key]}`).join(' · ')}</div>
      </div>)}
    </div>}
  </div>
}
