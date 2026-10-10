import { useEffect, useRef, useState } from 'react'
import EmployeeProfileModal from './EmployeeProfileModal'
import { veraApi } from '../lib/api'
import { canSharePdf, canSharePng, shareCustomerCountPdf, shareCustomerCountPng } from '../lib/customerCountShare'
import './CustomerCountShareDialog.css'

const formats = {
  pdf: { load: (...args) => veraApi.readCustomerCountPdf(...args), mime: 'application/pdf', canShare: canSharePdf, share: shareCustomerCountPdf },
  png: { load: (...args) => veraApi.readCustomerCountPng(...args), mime: 'image/png', canShare: canSharePng, share: shareCustomerCountPng },
}

function usePreparedReport(filters, format) {
  const [report, setReport] = useState(null)
  const [retry, setRetry] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    let active = true, objectUrl
    setReport(null)
    formats[format].load(filters, { signal: controller.signal }).then(blob => {
      if (!active) return
      const file = new File([blob], `VERA_SoLuongKhach.${format}`, { type: formats[format].mime })
      objectUrl = URL.createObjectURL(file)
      setReport({ filters, file, url: objectUrl })
    }).catch(error => {
      if (active) setReport({ filters, error: error.message || `Không tạo được báo cáo ${format.toUpperCase()}.` })
    })
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [filters, format, retry])
  // Do not leave a previous filter's download/share visible before effects run.
  return { ...(report?.filters === filters ? report : {}), retry: () => setRetry(value => value + 1) }
}

export default function CustomerCountShareDialog({ filters, onClose }) {
  const pdf = usePreparedReport(filters, 'pdf')
  const png = usePreparedReport(filters, 'png')
  const [error, setError] = useState('')
  const [sharing, setSharing] = useState('')
  const [message, setMessage] = useState('')
  const session = useRef(0)
  const sharingLock = useRef(false)
  useEffect(() => {
    session.current += 1
    sharingLock.current = false
    setSharing(''); setError(''); setMessage('')
    return () => { session.current += 1 }
  }, [filters])
  const share = (report, format) => {
    if (!report.file || sharingLock.current) return
    const currentSession = session.current
    sharingLock.current = true
    setError(''); setMessage(''); setSharing(format)
    const finish = () => {
      if (session.current !== currentSession) return
      sharingLock.current = false
      setSharing('')
    }
    const failure = e => {
      if (session.current === currentSession && e?.name !== 'AbortError') {
        setError(`Không mở được chia sẻ ${format.toUpperCase()}. Bạn có thể tải ${format.toUpperCase()} để gửi qua Zalo.`)
      }
    }
    try {
      // Both files are prepared before this click, with no fetch/render/await
      // before navigator.share. The user chooses the app and recipient.
      Promise.resolve(formats[format].share(report.file)).then(() => {
        if (session.current === currentSession) setMessage('Đã chuyển file sang ứng dụng chia sẻ.')
      }).catch(failure).finally(finish)
    } catch (e) { failure(e); finish() }
  }
  const pdfSupported = formats.pdf.canShare(pdf.file)
  const pngSupported = formats.png.canShare(png.file)
  return <EmployeeProfileModal className="customer-count-share-dialog" labelledBy="customer-count-share-title" onClose={onClose} busy={Boolean(sharing)}>
    <header><div><span className="eyebrow">VERA SPA · A4 ngang</span><h2 id="customer-count-share-title">Chia sẻ báo cáo số khách</h2></div><button type="button" className="secondary-button" onClick={onClose} disabled={Boolean(sharing)} aria-label="Đóng báo cáo số khách">✕</button></header>
    <p>Báo cáo theo bộ lọc hiện tại, có biểu đồ theo ngày. Mỗi hóa đơn được tính là một lượt khách.</p>
    {error && <p className="error-box" role="alert">{error}</p>}
    {message && <p role="status" data-system-feedback>{message}</p>}
    <div className="customer-count-share-formats">
      {[['pdf', pdf, pdfSupported], ['png', png, pngSupported]].map(([format, report, supported]) => <div key={format}>
        {!report.file && !report.error && <p role="status">Đang tạo {format.toUpperCase()}…</p>}
        {report.error && <><p className="error-box" role="alert">{report.error}</p><button type="button" className="secondary-button" onClick={report.retry} disabled={Boolean(sharing)}>Thử tạo lại {format.toUpperCase()}</button></>}
        {report.file && <div className="customer-count-share-ready"><strong>{format.toUpperCase()} đã sẵn sàng</strong><span>{format === 'pdf' ? 'A4 ngang' : 'Ảnh toàn bộ báo cáo'} · Biểu đồ và bảng số khách · {(report.file.size / 1024).toFixed(0)} KB</span><p>{supported ? 'Bấm Chia sẻ, sau đó chọn Zalo và người nhận.' : `Thiết bị này chưa hỗ trợ chia sẻ file ${format.toUpperCase()} trực tiếp. Tải ${format.toUpperCase()} rồi đính kèm trong Zalo.`}</p></div>}
      </div>)}
    </div>
    <footer>
      {pdf.file && <div className="customer-count-share-actions customer-count-share-pdf" role="group" aria-label="Báo cáo PDF">
        <a className="secondary-button" href={pdf.url} target="_blank" rel="noopener noreferrer">Xem PDF</a><a className="secondary-button" href={pdf.url} download={pdf.file.name}>Tải PDF</a>
        {pdfSupported && <button type="button" className="primary-button" onClick={() => share(pdf, 'pdf')} disabled={Boolean(sharing)}>{sharing === 'pdf' ? 'Đang mở chia sẻ…' : 'Chia sẻ qua Zalo'}</button>}
      </div>}
      {png.file && <div className="customer-count-share-actions customer-count-share-png" role="group" aria-label="Báo cáo PNG">
        <a className="secondary-button" href={png.url} download={png.file.name}>Tải PNG</a>
        {pngSupported && <button type="button" className="primary-button" onClick={() => share(png, 'png')} disabled={Boolean(sharing)}>{sharing === 'png' ? 'Đang mở chia sẻ…' : 'Chia sẻ PNG'}</button>}
      </div>}
    </footer>
  </EmployeeProfileModal>
}
