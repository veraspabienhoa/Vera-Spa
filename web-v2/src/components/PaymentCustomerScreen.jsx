import StableFeedback from './StableFeedback'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { paymentQrUrl, tipMoney, receiptNumber } from '../lib/paymentPresentation'

export default function PaymentCustomerScreen({ bank, amount, reference, settings }) {
  const [screen, setScreen] = useState(null)
  const [error, setError] = useState('')
  const [failedUrl, setFailedUrl] = useState('')
  const popup = useRef(null)
  const url = paymentQrUrl(bank, amount, reference)
  useEffect(() => () => { popup.current?.close() }, [])
  useEffect(() => {
    if ((!url || !settings?.enabled) && popup.current) { popup.current.close(); popup.current=null; setScreen(null) }
  }, [url, settings?.enabled])
  if (!settings?.enabled || !url) return null
  const open = () => {
    setError('')
    const target = popup.current?.closed === false ? popup.current : window.open('', '_blank', `popup=yes,width=${settings.width || 420},height=${settings.height || 600}`)
    if (!target) { setError('Trình duyệt đã chặn cửa sổ. Cho phép mở cửa sổ bật lên rồi thử lại.'); return }
    popup.current = target
    target.document.title = 'VERA SPA · Thanh toán'
    target.document.documentElement.lang = 'vi'
    target.document.body.style.margin = '0'
    setScreen(target.document.body)
    target.focus()
  }
  return <div className="customer-screen-control"><button type="button" className="secondary-button" onClick={open}>Mở màn hình QR cho khách</button><small>Có thể kéo cửa sổ sang màn hình phụ; trên điện thoại, mã mở trong tab riêng.</small><StableFeedback>{error && <p role="alert">{error}</p>}</StableFeedback>
    {screen && createPortal(<main style={{ boxSizing:'border-box', minHeight:'100vh', padding:20, textAlign:'center', fontFamily:'system-ui,sans-serif', background:'#fff', color:'#173329', display:'grid', alignContent:'center', justifyItems:'center', gap:12 }}><h1 style={{ margin:0, fontSize:24 }}>VERA SPA</h1><strong style={{ fontSize:30 }}>{tipMoney(amount)}</strong><p style={{ margin:0 }}>Nội dung: {receiptNumber(reference)}</p>{failedUrl === url ? <p role="alert">Không tải được QR. Vui lòng dùng thông tin tài khoản bên dưới.</p> : <img src={url} referrerPolicy="no-referrer" alt="Mã QR thanh toán" onError={() => setFailedUrl(url)} style={{ width:settings.qr_size || 300, maxWidth:'100%', height:'auto' }}/>}<strong>{bank.account_name}</strong><p style={{ margin:0 }}>{bank.bank_id} · {bank.account_no}</p><p>Vui lòng kiểm tra số tiền và tài khoản trước khi chuyển.</p><button onClick={() => { popup.current?.close(); popup.current=null; setScreen(null) }}>Đóng màn hình</button></main>,screen)}
  </div>
}
