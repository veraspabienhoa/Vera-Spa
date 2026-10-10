import { useEffect, useRef, useState } from 'react'
import { veraApi } from '../lib/api'

const types = { pdf: 'application/pdf', png: 'image/png' }
function canShare(file) { try { return Boolean(file && navigator.share && navigator.canShare?.({ files: [file] })) } catch { return false } }
function useReportFile(scope, format, onDenied) {
  const [result, setResult] = useState(null), [retry, setRetry] = useState(0)
  const denied = useRef(onDenied); denied.current = onDenied
  useEffect(() => {
    const controller = new AbortController(); let active = true, url
    setResult(null)
    veraApi.readTrainingReportExport(scope.employee, format, scope.filters, { signal: controller.signal }).then(blob => {
      if (!active) return
      const file = new File([blob], `VERA_DaoTao.${format}`, { type: types[format] })
      url = URL.createObjectURL(file); setResult({ scope, file, url })
    }).catch(error => {
      if (!active) return
      if ([401,403].includes(error.status)) { denied.current?.(error); return }
      setResult({ scope, error: error.message || `Không tạo được ${format.toUpperCase()}.` })
    })
    return () => { active = false; controller.abort(); if (url) URL.revokeObjectURL(url) }
  }, [scope, format, retry])
  return { ...(result?.scope === scope ? result : {}), retry: () => setRetry(n => n+1) }
}

export default function TrainingReportFiles({ scope, onDenied, onSharingChange }) {
  const pdf = useReportFile(scope, 'pdf', onDenied), png = useReportFile(scope, 'png', onDenied)
  const [sharing, setSharing] = useState(''), [feedback, setFeedback] = useState(null)
  const lock = useRef(false), session = useRef(0), notify = useRef(onSharingChange)
  notify.current = onSharingChange
  useEffect(() => {
    session.current += 1; lock.current = false; setSharing(''); setFeedback(null); notify.current?.(false)
    return () => { session.current += 1; notify.current?.(false) }
  }, [scope])
  const share = (report, format) => {
    if (lock.current || !report.file || !canShare(report.file)) return
    const current = session.current; lock.current = true; setSharing(format); setFeedback(null); notify.current?.(true)
    const finish = () => { if (current === session.current) { lock.current = false; setSharing(''); notify.current?.(false) } }
    const fail = error => { if (current === session.current && error?.name !== 'AbortError') setFeedback({ error: true, text: `Không mở được chia sẻ ${format.toUpperCase()}. Bạn có thể tải file để gửi.` }) }
    try {
      // Prepared files keep native sharing inside the original user click.
      Promise.resolve(navigator.share({ files: [report.file], title: 'Báo cáo đào tạo · VERA SPA' })).then(() => {
        if (current === session.current) setFeedback({ text: 'Đã chuyển file sang ứng dụng chia sẻ.' })
      }).catch(fail).finally(finish)
    } catch (error) { fail(error); finish() }
  }
  return <section className="training-report-files" aria-label="Xem, tải và chia sẻ báo cáo">
    <p>Toàn bộ dữ liệu theo nhân viên và khoảng ngày đang xem. PDF khổ A4 có lề; PNG là ảnh toàn bộ báo cáo.</p>
    {feedback && <p role={feedback.error ? 'alert' : 'status'} className={feedback.error ? 'error-box' : ''}>{feedback.text}</p>}
    {[['pdf',pdf],['png',png]].map(([format,report]) => <div className="training-report-file" key={format}>
      {!report.file && !report.error && <p role="status">Đang tạo {format.toUpperCase()}…</p>}
      {report.error && <><p role="alert" className="error-box">{report.error}</p><button type="button" className="secondary-button" disabled={Boolean(sharing)} onClick={report.retry}>Thử tạo lại {format.toUpperCase()}</button></>}
      {report.file && <><strong>{format === 'pdf' ? 'PDF A4' : 'Ảnh PNG'} · {(report.file.size/1024).toFixed(0)} KB</strong><div className="training-report-file-actions">
        <a className="secondary-button" href={report.url} target="_blank" rel="noopener noreferrer">Xem {format.toUpperCase()}</a>
        <a className="secondary-button" href={report.url} download={report.file.name}>Tải {format.toUpperCase()}</a>
        {canShare(report.file) ? <button type="button" className="primary-button" disabled={Boolean(sharing)} onClick={() => share(report,format)}>{sharing === format ? 'Đang mở chia sẻ…' : `Chia sẻ ${format.toUpperCase()}`}</button> : <small>Tải {format.toUpperCase()} rồi đính kèm trong ứng dụng cần chia sẻ.</small>}
      </div></>}
    </div>)}
  </section>
}
