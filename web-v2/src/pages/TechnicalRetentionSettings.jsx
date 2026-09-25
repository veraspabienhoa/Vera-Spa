import { useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const base = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''

async function request(method, days) {
  const session = await getCurrentSession()
  const response = await fetch(`${base}/v2/settings/technical-retention`, {
    method,
    headers: { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}) },
    ...(method === 'PUT' ? { body: JSON.stringify({ days }) } : {}),
  })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(result.detail || `HTTP ${response.status}`)
  return result
}

export default function TechnicalRetentionSettings() {
  const [days, setDays] = useState(3)
  const [busy, setBusy] = useState(true)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let active = true
    request('GET').then(value => { if (active) setDays(value.days) })
      .catch(error => { if (active) setMessage(error.message) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [])
  const save = async (event) => {
    event.preventDefault()
    setBusy(true); setMessage('')
    try { const value = await request('PUT', days); setDays(value.days); setMessage('Đã lưu. Lần dọn tiếp theo sẽ áp dụng cài đặt này.') }
    catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }
  return <section className="panel">
    <h2>Thời gian lưu nhật ký kỹ thuật</h2>
    <p>Chỉ dọn công việc cập nhật bảng tua đã hoàn tất. Booking, hóa đơn, lịch sử thao tác và công việc đang chờ vẫn được giữ.</p>
    <form onSubmit={save}>
      <label htmlFor="technical-retention-days">Giữ lại trong</label>{' '}
      <select id="technical-retention-days" value={days} disabled={busy} onChange={event => setDays(Number(event.target.value))}>
        {[1, 2, 3].map(value => <option key={value} value={value}>{value} ngày</option>)}
      </select>{' '}
      <button type="submit" disabled={busy}>{busy ? 'Đang xử lý…' : 'Lưu cài đặt'}</button>
    </form>
    {message && <p role="status">{message}</p>}
  </section>
}
