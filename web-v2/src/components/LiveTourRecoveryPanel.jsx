import { useCallback, useEffect, useState } from 'react'
import { veraApi } from '../lib/api'

export default function LiveTourRecoveryPanel({ isAdmin, onReload, actionBusy }) {
  const [status, setStatus] = useState(null)
  const [busy, setBusy] = useState(false)
  const [message, setMessage] = useState('')
  const check = useCallback(async () => {
    setBusy(true)
    try {
      setStatus(await veraApi.liveTourRecovery())
      setMessage('')
    } catch (error) {
      setMessage(error.message || 'Không kiểm tra được hàng đợi.')
    } finally {
      setBusy(false)
    }
  }, [])
  useEffect(() => { void check() }, [check])

  const retry = async () => {
    setBusy(true)
    try {
      const result = await veraApi.retryLiveTourRecovery()
      setMessage(result.requeued ? 'Đã đưa một tác vụ vào hàng đợi thử lại.' : 'Không có tác vụ an toàn để thử lại lúc này.')
      setStatus(await veraApi.liveTourRecovery())
    } catch (error) {
      setMessage(error.message || 'Không thử lại được tác vụ.')
    } finally {
      setBusy(false)
    }
  }
  const counts = status?.counts || {}
  const metrics = status?.metrics || {}
  const recoverable = Number(metrics.stale_processing || 0) + Number(counts.failed || 0)
  return <details className="panel live-tour-recovery">
    <summary>Khôi phục Live Tour {recoverable > 0 ? `· ${recoverable} tác vụ cần kiểm tra` : ''}</summary>
    <p>Dữ liệu hiển thị được tải từ bản đã lưu. Tác vụ đang ghi sẽ không bị ngắt.</p>
    <div className="live-tour-recovery-metrics" aria-live="polite">
      <span>Chờ: <strong>{counts.pending ?? '–'}</strong></span>
      <span>Đang chạy: <strong>{counts.processing ?? '–'}</strong></span>
      <span>Thử lại: <strong>{counts.retry ?? '–'}</strong></span>
      <span>Quá hạn: <strong>{metrics.stale_processing ?? '–'}</strong></span>
      <span>Thất bại: <strong>{counts.failed ?? '–'}</strong></span>
    </div>
    <div className="live-tour-recovery-actions">
      <button type="button" className="secondary-button" onClick={check} disabled={busy}>Kiểm tra hàng đợi</button>
      <button type="button" className="secondary-button" onClick={() => onReload()} disabled={actionBusy}>Tải bản đã lưu</button>
      {isAdmin && <button type="button" className="secondary-button" onClick={retry} disabled={busy || !recoverable}>Thử lại một tác vụ quá hạn</button>}
    </div>
    {message && <p role="status">{message}</p>}
    {status?.history?.length > 0 && <div className="live-tour-recovery-history">
      <strong>Lịch sử khôi phục</strong>
      <ul>{status.history.map((entry, index) => <li key={`${entry.job_id}-${index}`}>
        Tác vụ #{entry.job_id} · {entry.actor} · {new Date(entry.created_at).toLocaleString('vi-VN')}
      </li>)}</ul>
    </div>}
    <style>{`.live-tour-recovery{margin:12px 0;padding:16px}.live-tour-recovery summary{cursor:pointer;font-size:16px;font-weight:700}.live-tour-recovery p,.live-tour-recovery li{font-size:14px}.live-tour-recovery-metrics,.live-tour-recovery-actions{display:flex;flex-wrap:wrap;gap:12px;margin:12px 0}.live-tour-recovery-metrics span{padding:8px;border:1px solid #d8dee5;border-radius:8px}.live-tour-recovery-history ul{margin:8px 0;padding-left:22px}`}</style>
  </details>
}
