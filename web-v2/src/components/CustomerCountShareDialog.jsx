import { useEffect, useState } from 'react'
import EmployeeProfileModal from './EmployeeProfileModal'
import { veraApi } from '../lib/api'
import { canSharePdf, shareCustomerCountPdf } from '../lib/customerCountShare'
import './CustomerCountShareDialog.css'

export default function CustomerCountShareDialog({ filters, onClose }) {
  const [file, setFile] = useState(null)
  const [url, setUrl] = useState('')
  const [error, setError] = useState('')
  const [sharing, setSharing] = useState(false)
  const [retry, setRetry] = useState(0)
  const [message, setMessage] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    let active = true, objectUrl
    setFile(null); setUrl(''); setError(''); setMessage('')
    veraApi.readCustomerCountPdf(filters, { signal: controller.signal }).then(blob => {
      if (!active) return
      const prepared = new File([blob], 'VERA_SoLuongKhach.pdf', { type: 'application/pdf' })
      objectUrl = URL.createObjectURL(prepared)
      setFile(prepared); setUrl(objectUrl)
    }).catch(e => { if (active) setError(e.message || 'Không tạo được báo cáo PDF.') })
    return () => { active = false; controller.abort(); if (objectUrl) URL.revokeObjectURL(objectUrl) }
  }, [filters, retry])
  const share = () => {
    setError(''); setMessage(''); setSharing(true)
    try {
      // File is ready before this click. The user chooses Zalo and recipient
      // in the OS share sheet; a resolved promise does not prove delivery.
      Promise.resolve(shareCustomerCountPdf(file)).then(() => setMessage('Đã chuyển file sang ứng dụng chia sẻ.')).catch(e => {
        if (e.name !== 'AbortError') setError('Không mở được chia sẻ file. Bạn có thể tải PDF để gửi qua Zalo.')
      }).finally(() => setSharing(false))
    } catch (e) { setError(e.message); setSharing(false) }
  }
  const supported = file && canSharePdf(file)
  return <EmployeeProfileModal className="customer-count-share-dialog" labelledBy="customer-count-share-title" onClose={onClose} busy={sharing}>
    <header><div><span className="eyebrow">VERA SPA · A4 ngang</span><h2 id="customer-count-share-title">Chia sẻ báo cáo số khách</h2></div><button type="button" className="secondary-button" onClick={onClose} disabled={sharing} aria-label="Đóng báo cáo PDF">✕</button></header>
    <p>Báo cáo theo bộ lọc hiện tại, có biểu đồ theo ngày. Mỗi hóa đơn được tính là một lượt khách.</p>
    {!file && !error && <p role="status">Đang tạo PDF…</p>}
    {error && <p className="error-box" role="alert">{error}</p>}
    {message && <p role="status">{message}</p>}
    {file && <div className="customer-count-share-ready"><strong>PDF đã sẵn sàng</strong><span>A4 ngang · Biểu đồ và bảng số khách · {(file.size / 1024).toFixed(0)} KB</span><p>{supported ? 'Bấm Chia sẻ, sau đó chọn Zalo và người nhận.' : 'Thiết bị này chưa hỗ trợ chia sẻ file trực tiếp. Tải PDF rồi đính kèm trong Zalo.'}</p></div>}
    <footer>
      {!file && error && <button type="button" className="secondary-button" onClick={() => setRetry(value => value + 1)}>Thử tạo lại</button>}
      {file && <><a className="secondary-button" href={url} target="_blank" rel="noopener noreferrer">Xem PDF</a><a className="secondary-button" href={url} download={file.name}>Tải PDF</a>{supported && <button type="button" className="primary-button" onClick={share} disabled={sharing}>{sharing ? 'Đang mở chia sẻ…' : 'Chia sẻ qua Zalo'}</button>}</>}
    </footer>
  </EmployeeProfileModal>
}
