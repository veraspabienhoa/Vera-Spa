import { invoiceServiceSubtotal } from '../lib/liveTourInvoiceMoney'
import StableFeedback from './StableFeedback'
import UiToolbar from './UiToolbar'
import UiCustomText from './UiCustomText'
import { formatVeraDate } from '../lib/veraDate'
import VeraDateTimeInput from './VeraDateTimeInput'
import { isComboRedemption, usesComboTicket } from '../lib/paymentPresentation'
import { invoiceLocalTime } from '../lib/liveTourFilters'
import { useState } from 'react'
import { Trash2, X } from 'lucide-react'
import useDialogFocus from '../lib/useDialogFocus'
import VeraMoneyInput from './VeraMoneyInput'
import './LiveTourBookingDialog.css'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import { bookingServiceItems, bookingTotal } from '../lib/liveTourBooking'
import { catalogIsAvailable } from '../lib/serviceCatalog'

const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')} đ`

export default function LiveTourPaidInvoiceDialog({ context, catalog = [], busy, error, onAction, onClose, canEditDate = false, isAdmin = false }) {
  const { item, mode, revision } = context
  const deleting = mode === 'delete'
  const dialog = useDialogFocus(() => { if (!busy) onClose() })
  const [prices, setPrices] = useState(() => item.entries.map((entry) => String(entry.price || 0)))
  const [initialItems] = useState(() => item.entries.map(entry => bookingServiceItems(entry, catalog)))
  const [serviceItems, setServiceItems] = useState(initialItems)
  const [editedRows, setEditedRows] = useState({})
  const canChangeServices = !item.purchased_combo_id && !item.combo_purchase_id && item.payment_method !== 'COMBO' && !item.entries.some(entry => entry.combo_purchase_id)
  const setItems = (index, items) => {
    setEditedRows(current => ({ ...current, [index]: true }))
    setServiceItems(current => current.map((row, i) => i === index ? items : row))
    setPrices(current => current.map((price, i) => i === index ? String(bookingTotal(items, catalog)) : price))
  }
  const [discount, setDiscount] = useState(String(isComboRedemption(item) ? 0 : item.discount || 0))
  const [tip, setTip] = useState(String(item.tip || 0))
  const [method, setMethod] = useState(item.payment_method)
  const [note, setNote] = useState(item.note ?? '')
  const [reason, setReason] = useState('')
  const [invoiceAt, setInvoiceAt] = useState(() => invoiceLocalTime(item))
  const covered = isComboRedemption(item)
  const subtotal = covered ? invoiceServiceSubtotal(item) : prices.reduce((sum, price) => sum + Number(price || 0), 0)
  const total = subtotal - Number(discount || 0) + Number(tip || 0)
  const submit = async (event) => {
    event.preventDefault()
    if (busy) return
    const entries = prices.flatMap((price, index) => {
      const changed = canChangeServices && JSON.stringify(serviceItems[index]) !== JSON.stringify(initialItems[index])
      return changed || Number(price) !== Number(item.entries[index].price)
        ? [{ index, price: Number(price), ...(changed ? { service_items: serviceItems[index] } : {}) }] : []
    })
    const result = await onAction(deleting ? 'paid_invoice_delete' : 'paid_invoice_update', {
      invoice_id: item.id, reason: reason.trim(),
      ...(!deleting && canEditDate && invoiceAt !== invoiceLocalTime(item) ? { invoice_at: `${invoiceAt}:00+07:00` } : {}),
      ...(!deleting ? { entries, discount: Number(discount), tip: Number(tip), payment_method: method } : {}),
      ...(!deleting && note !== (item.note ?? '') ? { note } : {}),
    }, [], { expectedRevision: revision })
    if (result) onClose()
  }
  return <div className="live-tour-modal-backdrop" onMouseDown={event => { if (event.target === event.currentTarget && !busy) onClose() }}>
    <section data-ui-key="u-022439885343" ref={dialog} tabIndex="-1" className="live-tour-modal tour-booking-dialog" role="dialog" aria-modal="true" aria-label={`${deleting ? 'Hủy' : 'Sửa'} hóa đơn đã thanh toán`} onClick={(event) => event.stopPropagation()}>
      <div className="live-tour-modal-head"><strong>{deleting ? 'Xóa / hủy' : 'Sửa'} hóa đơn đã thanh toán</strong><button data-dialog-close="true" data-ui-key="u-9dbbb3e4bef1" type="button" className="icon-button" aria-label="Đóng" disabled={busy} onClick={onClose}><X size={18}/></button></div>
      <p className={usesComboTicket(item) ? 'vera-combo-ticket' : undefined}>{usesComboTicket(item) && <strong className="vera-combo-badge">VÉ COMBO</strong>}<strong>{item.bill_no} · {item.customer_name || 'Khách lẻ'}</strong><br/>{formatVeraDate(item.business_date)} · {item.payment_method} · {money(item.total)}</p>
      <StableFeedback>{error && <p className="error-box" role="alert">{error} Nếu dữ liệu đã thay đổi, hãy đóng cửa sổ và mở lại bản mới nhất.</p>}</StableFeedback>
      <p className={deleting ? 'error-box' : 'setup-note'}>{deleting
        ? isAdmin
          ? 'Admin có thể hủy hóa đơn ở mọi ngày. Tiền và TIP của hóa đơn được loại khỏi báo cáo. Lượt combo được hoàn theo lịch sử gốc. Nếu hủy hóa đơn bán combo đã dùng hoặc đang giữ chỗ, số dư và booking combo được giữ nguyên; admin có thể điều chỉnh combo riêng. Bản gốc được giữ trong lịch sử.'
          : 'Hủy hóa đơn sẽ loại tiền và TIP khỏi báo cáo, hoàn vé đã dùng theo lịch sử gốc. Hóa đơn bán combo chỉ được hủy khi combo chưa dùng và không còn booking giữ chỗ. Bản gốc được giữ trong lịch sử.'
        : 'Tìm, thêm/bỏ dịch vụ, sửa số lượng, giá, giảm giá, TIP, ghi chú hoặc phương thức thu tiền. Giữ nguyên khách hàng, nhân viên, số bill và kết quả hoàn thành. Hóa đơn combo cần hủy và lập lại nếu đổi dịch vụ hoặc đổi qua lại COMBO để đối soát vé.'}</p>
      <p>Đây là điều chỉnh sổ hệ thống; không tự hoàn tiền qua ngân hàng hoặc thẻ. Cần đối soát thu/hoàn tiền thực tế riêng.</p>
      <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
        {!deleting && canEditDate && true && <label className="live-tour-field wide"><span>Ngày giờ hóa đơn (giờ Việt Nam)</span><VeraDateTimeInput required value={invoiceAt} onChange={e => setInvoiceAt(e.target.value)}/></label>}
        {item.entries.map((entry, index) => <div data-ui-key="u-f3166d51ac8c" className="wide live-tour-data-card" key={index}><strong>{entry.employee_name || 'Bán combo'} · {entry.service}</strong><small>{entry.room}</small>{entry.note && <small style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>Ghi chú booking: {entry.note}</small>}
          {!deleting && canChangeServices && <>
            <LiveTourSearchSelect label="Thêm dịch vụ" placeholder="Tìm và chọn dịch vụ" clearOnSelect value="" disabled={busy}
              options={catalog.filter(service => catalogIsAvailable(service) && !serviceItems[index].some(part => part.service_id === service.id)).map(service => ({ value: service.id, label: service.name, detail: money(service.price) }))}
              onChange={id => { if (id) setItems(index, [...serviceItems[index], { service_id: id, quantity: 1 }]) }}/>
            {serviceItems[index].map((part, partIndex) => <div className="tour-booking-item" key={part.service_id}>
              <span>{catalog.find(service => service.id === part.service_id)?.name || entry.service_items?.find(service => service.service_id === part.service_id)?.name || part.service_id}</span>
              <label>Số lượng<input type="number" required min="1" max="30" value={part.quantity} onChange={event => setItems(index, serviceItems[index].map((value, i) => i === partIndex ? { ...value, quantity: Number(event.target.value) } : value))}/></label>
              <button className="icon-button" type="button" aria-label={`Bỏ dịch vụ ${partIndex + 1} của ${entry.employee_name}`} onClick={() => setItems(index, serviceItems[index].filter((_, i) => i !== partIndex))}><Trash2 size={16}/></button>
            </div>)}
            {!serviceItems[index].length && <small>{initialItems[index].length ? 'Chọn ít nhất một dịch vụ để lưu thay đổi.' : `Dịch vụ gốc: ${entry.service}. Chọn dịch vụ nếu cần thay đổi.`}</small>}
          </>}
          {deleting ? <span>{money(covered ? entry.combo_extra_subtotal || 0 : entry.price)}</span> : <label className="live-tour-field"><span>Giá dòng dịch vụ (đ)</span><VeraMoneyInput max="10000000000" required disabled={covered} value={covered ? String(entry.combo_extra_subtotal || 0) : prices[index]} onChange={(event) => setPrices((current) => current.map((price, i) => i === index ? event.target.value : price))}/></label>}
        </div>)}
        {!deleting && <>
          <label className="live-tour-field"><span>Giảm giá (đ)</span><VeraMoneyInput max={subtotal} required disabled={covered} value={discount} onChange={(event) => setDiscount(event.target.value)}/></label>
          <label className="live-tour-field"><span>TIP (đ)</span><VeraMoneyInput max="10000000000" required value={tip} onChange={(event) => setTip(event.target.value)}/></label>
          <label className="live-tour-field wide"><span>Phương thức thu tiền</span><select value={method} disabled={item.payment_method === 'COMBO'} onChange={(event) => setMethod(event.target.value)}>{(item.payment_method === 'COMBO' ? ['COMBO'] : ['TIỀN MẶT', 'CHUYỂN KHOẢN', 'THẺ']).map((value) => <option key={value}>{value}</option>)}</select></label>
          <label className="live-tour-field wide"><span>Ghi chú hóa đơn</span><textarea maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)}/></label>
          <div className="wide tour-booking-total"><span>Tổng tiền sau sửa{covered ? ' (combo đã trả trước)' : ''}</span><strong>{money(total)}</strong></div>
        </>}
        {deleting && item.note && <p className="wide" style={{ whiteSpace: 'pre-wrap', overflowWrap: 'anywhere' }}>Ghi chú hóa đơn: {item.note}</p>}
        <label className="live-tour-field wide"><span>Lý do {deleting ? 'hủy' : 'sửa'}{isAdmin ? ' (không bắt buộc)' : ' *'}</span><textarea required={!isAdmin} maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)}/></label>
        <UiToolbar data-ui-key="u-04c00bbd323b" className="live-tour-modal-actions wide"><button data-dialog-close="true" data-ui-key="u-ad34181f38ce" data-ui-label-default="Đóng" type="button" className="secondary-button" onClick={onClose}><UiCustomText uiKey="u-ad34181f38ce">Đóng</UiCustomText></button><button data-ui-key="u-03d2b0024e0c" className={deleting ? 'secondary-button danger-button' : 'primary-button'} type="submit" disabled={(!isAdmin && !reason.trim()) || (!deleting && canChangeServices && serviceItems.some((items, index) => !items.length && editedRows[index]))}>{deleting ? 'Xác nhận hủy hóa đơn' : 'Lưu điều chỉnh hóa đơn'}</button></UiToolbar>
      </fieldset></form>
    </section>
  </div>
}
