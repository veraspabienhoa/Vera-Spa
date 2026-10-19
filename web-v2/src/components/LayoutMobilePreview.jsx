import { useState } from 'react'
import { createPortal } from 'react-dom'
import { confirmDialog } from '../lib/systemDialogs'

export default function LayoutMobilePreview({ page, onClose }) {
  const [width, setWidth] = useState(390)
  const url = new URL(window.location.href)
  url.search = ''
  url.hash = ''
  url.searchParams.set('standalone', '1')
  url.searchParams.set('page', page)
  url.searchParams.set('layoutPreview', 'mobile')
  const close = async () => {
    if (await confirmDialog('Đóng xem trước Mobile? Hãy lưu bố cục trong khung trước khi đóng; thay đổi chưa lưu sẽ bị bỏ.')) onClose()
  }
  return createPortal(<div className="layout-mobile-preview" role="dialog" aria-modal="true" aria-label="Chỉnh giao diện Mobile trên desktop">
    <header><strong>Chỉnh giao diện Mobile</strong><label>Chiều rộng<select value={width} onChange={e=>setWidth(Number(e.target.value))}>{[360,390,430].map(value=><option key={value} value={value}>{value} px</option>)}</select></label><button type="button" onClick={close}>Đóng</button></header>
    <p>Trong khung điện thoại, chọn Tùy chỉnh để kéo thả. Bấm Lưu để áp dụng riêng cho Mobile.</p>
    <iframe title="Giao diện Mobile" src={url.href} style={{width}}/>
  </div>, document.body)
}
