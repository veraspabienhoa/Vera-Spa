import { useState } from 'react'
import { Trash2, X } from 'lucide-react'
import { bookingServiceItems, bookingTotal } from '../lib/liveTourBooking'
import { catalogIsAvailable } from '../lib/serviceCatalog'
import useDialogFocus from '../lib/useDialogFocus'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import './LiveTourBookingDialog.css'

const money = (value) => `${Number(value || 0).toLocaleString('vi-VN')} đ`

export default function LiveTourPendingDialog({ context, catalog, busy, error, onAction, onClose }) {
  const { item, mode, revision } = context
  const editing = mode === 'edit'
  const deleting = mode === 'delete'
  const dialog = useDialogFocus(() => { if (!busy) onClose() })
  const [initial] = useState(() => item.entries.map((entry) => ({ items: bookingServiceItems(entry, catalog), price: entry.price || 0 })))
  const [rows, setRows] = useState(initial)
  const [note, setNote] = useState(item.note || '')
  const [reason, setReason] = useState('')
  const setItems = (index, items) => setRows((current) => current.map((row, i) => i === index ? { items, price: bookingTotal(items, catalog) } : row))
  const submit = async (event) => {
    event.preventDefault()
    const entries = rows.flatMap((row, index) => {
      const changed = JSON.stringify(row.items) !== JSON.stringify(initial[index].items)
      const priceChanged = Number(row.price) !== Number(initial[index].price)
      return changed || priceChanged ? [{ index, ...(changed ? { service_items: row.items } : {}), price: Number(row.price) }] : []
    })
    const result = await onAction(deleting ? 'pending_delete' : 'pending_update', {
      pending_id: item.id, reason: reason.trim(), ...(editing ? { note, entries } : {}),
    }, [], { expectedRevision: revision })
    if (result) onClose()
  }
  return <div className="live-tour-modal-backdrop" onClick={() => { if (!busy) onClose() }}>
    <section ref={dialog} tabIndex="-1" className="live-tour-modal tour-booking-dialog" role="dialog" aria-modal="true" aria-label={deleting ? 'Xóa hóa đơn chờ thanh toán' : editing ? 'Sửa hóa đơn chờ thanh toán' : 'Xem hóa đơn chờ thanh toán'} onClick={(event) => event.stopPropagation()}>
      <div className="live-tour-modal-head"><strong>{deleting ? 'Xóa' : editing ? 'Sửa' : 'Xem'} hóa đơn chờ thanh toán</strong><button type="button" className="icon-button" aria-label="Đóng" disabled={busy} onClick={onClose}><X size={18}/></button></div>
      <p><strong>{item.customer_name || 'Khách lẻ'}</strong>{item.customer_phone && ` · ${item.customer_phone}`}<br/><small>Mã: {item.id} · {item.created_at}</small></p>
      {error && <p className="error-box" role="alert">{error} Nếu dữ liệu đã thay đổi, hãy đóng cửa sổ và mở lại bản mới nhất trước khi sửa.</p>}
      {deleting && <p className="error-box">Xóa phiếu khỏi Chờ thanh toán và giải phóng vé combo đang giữ chỗ. Không trừ vé, không đổi doanh thu đã thu. Bản cũ và lý do được lưu trong lịch sử để đối chiếu.</p>}
      {editing && <p>Giữ nguyên khách hàng, nhân viên và kết quả hoàn thành. Dịch vụ không đổi giữ giá đã ghi nhận; khi đổi dịch vụ, hệ thống kiểm tra lại vé combo.</p>}
      <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
        {item.entries.map((entry, index) => <div className="wide live-tour-data-card" key={index}>
          <strong>{entry.employee_name} · {entry.room}</strong>
          {editing ? <>
            <LiveTourSearchSelect label="Thêm dịch vụ" clearOnSelect value="" options={catalog.filter((service) => catalogIsAvailable(service) && !rows[index].items.some((part) => part.service_id === service.id)).map((service) => ({ value: service.id, label: service.name, detail: money(service.price) }))} onChange={(id) => { if (id) setItems(index, [...rows[index].items, { service_id: id, quantity: 1 }]) }}/>
            {rows[index].items.map((part, partIndex) => <div className="tour-booking-item" key={part.service_id}>
              <span>{catalog.find((service) => service.id === part.service_id)?.name || entry.service_items?.find((service) => service.service_id === part.service_id)?.name || part.service_id}</span>
              <label>Số lượng<input type="number" required min="1" max="30" value={part.quantity} onChange={(event) => setItems(index, rows[index].items.map((value, i) => i === partIndex ? { ...value, quantity: Number(event.target.value) } : value))}/></label>
              <button className="icon-button" type="button" aria-label={`Bỏ dịch vụ ${partIndex + 1} của ${entry.employee_name}`} onClick={() => setItems(index, rows[index].items.filter((_, i) => i !== partIndex))}><Trash2 size={16}/></button>
            </div>)}
            {!rows[index].items.length && <small>Dịch vụ gốc: {entry.service}. Chọn dịch vụ nếu cần thay đổi.</small>}
            <label className="live-tour-field"><span>Giá dòng dịch vụ (đ)</span><input type="number" min="0" max="10000000000" step="1" required value={rows[index].price} onChange={(event) => setRows((current) => current.map((row, i) => i === index ? { ...row, price: event.target.value } : row))}/></label>
          </> : <><span>{entry.service}</span><strong>{money(entry.price)}</strong></>}
          {entry.combo_purchase_id && <small>Giữ chỗ combo: {entry.combo_reserved_units || 0} vé · số vé được kiểm tra lại khi thay đổi dịch vụ.</small>}
        </div>)}
        <div className="wide tour-booking-total"><span>Tổng tiền dịch vụ</span><strong>{money(rows.reduce((sum, row) => sum + Number(row.price || 0), 0))}</strong></div>
        {editing ? <label className="live-tour-field wide"><span>Ghi chú</span><textarea maxLength={2000} value={note} onChange={(event) => setNote(event.target.value)}/></label> : <p className="wide">Ghi chú: {item.note || '—'}</p>}
        {(editing || deleting) && <label className="live-tour-field wide"><span>Lý do {deleting ? 'xóa' : 'sửa'} *</span><textarea required maxLength={1000} value={reason} onChange={(event) => setReason(event.target.value)}/></label>}
        <div className="live-tour-modal-actions wide"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button>{(editing || deleting) && <button className={deleting ? 'secondary-button danger-button' : 'primary-button'} type="submit" disabled={!reason.trim()}>{deleting ? 'Xác nhận xóa hóa đơn chờ' : 'Lưu sửa hóa đơn'}</button>}</div>
      </fieldset></form>
    </section>
  </div>
}
