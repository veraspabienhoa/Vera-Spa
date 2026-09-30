import { useState } from 'react'
import { veraApi } from '../lib/api'

export default function LeaveQueuePolicyRules({ policy, canEdit }) {
  const [current, setCurrent] = useState(policy)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const selected = current.enabled ? current.reasons : []
  async function save(reasons) {
    if (!canEdit || busy) return
    setBusy(true); setError(''); setMessage('')
    try {
      const result = await veraApi.saveLeaveQueuePolicy({ enabled: reasons.length > 0, reasons, expected_revision: current.revision })
      setCurrent(result); setMessage(result.message)
    } catch (err) { setError(err.message) }
    finally { setBusy(false) }
  }
  return <section className="panel leave-queue-policy-panel" aria-labelledby="leave-queue-policy-title">
    <h2 id="leave-queue-policy-title">XẾP CUỐI BẢNG TUA · 03:00</h2>
    <p>Mỗi ngày chỉ sắp xếp một lần lúc 03:00 giờ Việt Nam, theo lý do ngày hôm trước được bật bên dưới. Sau đó bảng tua vận hành bình thường; check-in không xếp lại.</p>
    <p>Đang bật {selected.length}/{current.available_reasons.length} lý do. Thay đổi được tự động lưu và áp dụng tại lượt 03:00 kế tiếp.</p>
    {canEdit && <div className="leave-queue-policy-actions">
      <button type="button" disabled={busy || selected.length === current.available_reasons.length} onClick={() => save(current.available_reasons)}>Kích hoạt tất cả</button>
      <button type="button" disabled={busy || selected.length === 0} onClick={() => save([])}>Tắt tất cả</button>
    </div>}
    <fieldset disabled={!canEdit || busy}>
      <legend>Lý do áp dụng</legend>
      {current.available_reasons.map(reason => <label key={reason}>
        <input type="checkbox" checked={selected.includes(reason)} onChange={event => save(event.target.checked ? [...selected, reason] : selected.filter(item => item !== reason))} />
        <span>{reason}</span>
      </label>)}
    </fieldset>
    {!canEdit && <p>Chỉ Admin được thay đổi nội quy này.</p>}
    {busy && <p role="status">Đang lưu…</p>}
    {message && <p role="status">{message}</p>}
    {error && <p role="alert">{error}</p>}
  </section>
}
