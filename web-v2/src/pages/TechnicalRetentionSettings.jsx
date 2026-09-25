import { useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'
import { apiBase } from '../lib/apiConfig'
import { formatVeraDateTime } from '../lib/veraDate'

async function request(method, settings) {
  const session = await getCurrentSession()
  const response = await fetch(`${apiBase}/v2/settings/technical-retention`, {
    method,
    signal: AbortSignal.timeout(15000),
    headers: { 'Content-Type': 'application/json', ...(session?.access_token ? { Authorization: `Bearer ${session.access_token}` } : {}) },
    ...(method === 'PUT' ? { body: JSON.stringify(settings) } : {}),
  })
  const result = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(typeof result.detail === 'string' ? result.detail : `HTTP ${response.status}`)
  if (!Number.isInteger(result.cleanup_interval_hours)) {
    throw new Error('Máy chủ chưa hỗ trợ cài đặt chu kỳ dọn. Hãy chạy Deploy VPS Production rồi tải lại.')
  }
  return result
}

export default function TechnicalRetentionSettings() {
  const [days, setDays] = useState(3)
  const [hours, setHours] = useState('1')
  const [saved, setSaved] = useState(null)
  const [busy, setBusy] = useState(true)
  const [message, setMessage] = useState('')
  useEffect(() => {
    let active = true
    request('GET').then(value => { if (active) { setDays(value.days); setHours(String(value.cleanup_interval_hours ?? 1)); setSaved(value) } })
      .catch(error => { if (active) setMessage(error.message) })
      .finally(() => { if (active) setBusy(false) })
    return () => { active = false }
  }, [])
  const reload = async () => {
    setBusy(true); setMessage('')
    try {
      const value = await request('GET')
      setDays(value.days); setHours(String(value.cleanup_interval_hours ?? 1)); setSaved(value)
    } catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }
  const validHours = /^\d+$/.test(hours) && Number(hours) >= 1 && Number(hours) <= 168
  const save = async (event) => {
    event.preventDefault()
    if (busy || !saved || !validHours) return
    setBusy(true); setMessage('')
    try {
      const value = await request('PUT', { days, cleanup_interval_hours: Number(hours) })
      setDays(value.days); setHours(String(value.cleanup_interval_hours)); setSaved(value)
      setMessage('Đã lưu chu kỳ dọn Live Tour. Lịch nền sẽ áp dụng cài đặt mới.')
    }
    catch (error) { setMessage(error.message) }
    finally { setBusy(false) }
  }
  return <section className="panel">
    <h2>Lưu nhật ký và dọn Live Tour tự động</h2>
    <p>Chỉ dọn công việc cập nhật bảng tua đã hoàn tất. Booking, hóa đơn, lịch sử thao tác và công việc đang chờ vẫn được giữ.</p>
    <form onSubmit={save}>
      <p><label htmlFor="technical-retention-days">Giữ lại nhật ký trong</label>{' '}
      <select id="technical-retention-days" value={days} disabled={busy || !saved} onChange={event => setDays(Number(event.target.value))}>
        {[1, 2, 3].map(value => <option key={value} value={value}>{value} ngày</option>)}
      </select></p>
      <p><label htmlFor="technical-cleanup-hours">Tự động dọn Live Tour mỗi</label>{' '}
      <input id="technical-cleanup-hours" type="number" inputMode="numeric" min="1" max="168" step="1" required
        aria-describedby="technical-cleanup-help" value={hours} disabled={busy || !saved}
        onChange={event => setHours(event.target.value)} style={{ width: '6rem', maxWidth: '100%' }} /> giờ</p>
      <p id="technical-cleanup-help">Nhập từ 1 đến 168 giờ. Hệ thống kiểm tra lịch mỗi 5 phút và chỉ dọn khi đến hạn, kể cả khi bạn đóng trang.</p>
      <button type="submit" disabled={busy || !saved || !validHours}>{busy ? 'Đang xử lý…' : 'Lưu cài đặt'}</button>{' '}
      <button type="button" disabled={busy} onClick={reload}>Tải lại cài đặt và trạng thái</button>
    </form>
    {saved && <div>
      <p>Chu kỳ đã lưu: mỗi {saved.cleanup_interval_hours ?? 1} giờ.</p>
      <p>Lần dọn thành công gần nhất: {formatVeraDateTime(saved.last_cleanup_at, 'Chưa ghi nhận')}.</p>
      {saved.last_cleanup_at && <p>Đã dọn {saved.last_cleanup_removed ?? 0} bản ghi kỹ thuật trong lần đó.</p>}
      <p>Hạn dọn tiếp theo: {formatVeraDateTime(saved.next_cleanup_at, 'Lần kiểm tra lịch kế tiếp')}.</p>
    </div>}
    {message && <p role="status">{message}</p>}
  </section>
}
