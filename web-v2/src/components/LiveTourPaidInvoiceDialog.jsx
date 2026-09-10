import { invoiceLocalTime } from '../lib/liveTourFilters'
import { useState } from 'react'
import { X } from 'lucide-react'
import useDialogFocus from '../lib/useDialogFocus'
import './LiveTourBookingDialog.css'

const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')} đ`

export default function LiveTourPaidInvoiceDialog({ context, busy, error, onAction, onClose, canEditDate = false }) {
  const { item, mode, revision } = context
  const deleting = mode === 'delete'
  const dialog = useDialogFocus(() => { if (!busy) onClose() })
  const [prices, setPrices] = useState(() => item.entries.map((entry) => String(entry.price || 0)))
  const [discount, setDiscount] = useState(String(item.discount || 0))
  const [tip, setTip] = useState(String(item.tip || 0))
  const [method, setMethod] = useState(item.payment_method)
  const [note, setNote] = useState(item.note || '')
  const [reason, setReason] = useState('')
  const [invoiceAt, setInvoiceAt] = useState(() => invoiceLocalTime(item))
  const covered = item.combo_units_source === 'server_purchase_components'
  const subtotal = prices.reduce((sum, price) => sum + Number(price || 0), 0)
  const total = covered ? Number(tip || 0) : subtotal - Number(discount || 0) + Number(tip || 0)
  const submit = async (event) => {
    event.preventDefault()
    const entries = prices.flatMap((price, index) => Number(price) !== Number(item.entries[index].price) ? [{ index, price: Number(price) }] : [])
    const result = await onAction(deleting ? 'paid_invoice_delete' : 'paid_invoice_update', {
      invoice_id: item.id, reason: reason.trim(),
      ...(!deleting && canEditDate && invoiceAt !== invoiceLocalTime(item) ? { invoice_at: `${invoiceAt}:00+07:00` } : {}),
      ...(!deleting ? { entries, discount: Number(discount), tip: Number(tip), payment_method: method, note } : {}),
    }, [], { expectedRevision: revision })
    if (result) onClose()
  }
  return <div className="live-tour-modal-backdrop" onClick={() => { if (!busy) onClose() }}>
    <section ref={dialog} tabIndex="-1" className="live-tour-modal tour-booking-dialog" role="dialog" aria-modal="true" aria-label={`${deleting ? 'Hủy' : 'Sửa'} hóa đơn đã thanh toán`} onClick={(event) => event.stopPropagation()}>
      <div className="live-tour-modal-head"><strong>{deleting ? 'Xóa / hủy' : 'Sửa'} hóa đơn đã thanh toán</strong><button type="button" className="icon-button" aria-label="Đóng" disabled={busy} onClick={onClose}><X size={18}/></button></div>
      <p><strong>{item.bill_no} · {item.customer_name || 'Khách lẻ'}</strong><br/>{item.business_date} · {item.payment_method} · {money(item.total)}</p>
      {error && <p className="error-box" role="alert">{error} Nếu dữ liệu đã thay đổi, hãy đóng cửa sổ và mở lại bản mới nhất.</p>}
      <p className={deleting ? 'error-box' : 'setup-note'}>{deleting
        ? 'Hủy hóa đơn sẽ loại tiền và TIP khỏi báo cáo, hoàn vé đã dùng theo lịch sử gốc. Hóa đơn bán combo chỉ được hủy khi combo chưa dùng và không còn booking giữ chỗ. Bản gốc được giữ trong lịch sử.'
        : 'Sửa giá, giảm giá, TIP, ghi chú hoặc phương thức thu tiền. Khách hàng, dịch vụ, nhân viên, số bill được giữ nguyên. Muốn đổi dịch vụ hoặc đổi qua lại COMBO: hủy rồi lập lại để đối soát vé.'}</p>
      <p>Đây là điều chỉnh sổ hệ thống; không tự hoàn tiền qua ngân hàng hoặc thẻ. Cần đối soát thu/hoàn tiền thực tế riêng.</p>
      <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
        {!deleting && canEditDate && true && <label className="live-tour-field wide"><span>Ngày giờ hóa đơn (giờ Việt Nam)</span><input type="datetime-local" required value={invoiceAt} onChange={e => setInvoiceAt(e.target.value)}/></label>}
        {item.entries.map((entry, index) => <div className="wide live-tour-data-card" key={index}><strong>{entry.employee_name || 'Bán combo'} · {entry.service}</strong><small>{entry.room}</small>
          {deleting ? <span>{money(entry.price)}</span> : <label className="live-tour-field"><span>Giá dòng dịch vụ (đ)</span><input type="number" min="0" max="10000000000" step="1" required value={prices[index]} onChange={(event) => setPrices((current) => current.map((price, i) => i === index ? event.target.value : price))}/></label>}
        </div>)}
        {!deleting && <>
          <label className="live-tour-field"><span>Giảm giá (đ)</span><input type="number" min="0" max={subtotal} step="1" required disabled={covered} value={discount} onChange={(event) => setDiscount(event.target.value)}/></label>
          <label className="live-tour-field"><span>TIP (đ)</span><input type="number" min="0" max="10000000000" step="1" required value={tip} onChange={(event) => setTip(event.target.value)}/></label>
          <label className="live-tour-field wide"><span>Phương thức thu tiền</span><select value={method} disabled={item.payment_method === 'COMBO'} onChange={(event) => setMethod(event.target.value)}>{(item.payment_method === 'COMBO' ? ['COMBO'] : ['TIỀN MẶT', 'CHUYỂN KHOẢN', 'THẺ']).map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="live-tour-field wide"><span>Ghi chú</span><textarea maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)}/></label>
          <div className="wide tour-booking-total"><span>Tổng tiền sau sửa{covered ? ' (combo đã trả trước)' : ''}</span><strong>{money(total)}</strong></div>
        </>}
        <label className="live-tour-field wide"><span>Lý do {deleting ? 'hủy' : 'sửa'} *</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)}/></label>
        <div className="live-tour-modal-actions wide"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button><button className={deleting ? 'secondary-button danger-button' : 'primary-button'} type="submit" disabled={!reason.trim()}>{deleting ? 'Xác nhận hủy hóa đơn' : 'Lưu điều chỉnh hóa đơn'}</button></div>
      </fieldset></form>
    </section>
  </div>
}
