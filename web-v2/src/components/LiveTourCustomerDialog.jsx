import { useState } from 'react'
import useDialogFocus from '../lib/useDialogFocus'
import './LiveTourBookingDialog.css'
export default function LiveTourCustomerDialog({ context, busy, error, onAction, onClose }) {
  const { customer, purchase, mode, revision } = context
  const deleting = mode === 'delete'
  const ref = useDialogFocus(() => { if (!busy) onClose() })
  const [name, setName] = useState(customer.name || '')
  const [phone, setPhone] = useState(customer.phone || '')
  const [remaining, setRemaining] = useState(purchase?.remaining ?? 0)
  const [parts, setParts] = useState(purchase?.component_balances?.map(p => ({ ...p })) || [])
  const [note, setNote] = useState(purchase?.note || '')
  const [reason, setReason] = useState('')
  const title = `${deleting ? 'Xóa' : 'Sửa'} ${purchase ? 'combo của khách' : 'khách hàng'}`
  const submit = async e => {
    e.preventDefault()
    const action = purchase ? `customer_combo_${deleting ? 'delete' : 'update'}` : deleting ? 'customer_delete' : 'customer_upsert'
    const payload = { customer_id: customer.id, reason: reason.trim(), ...(purchase ? { purchase_id: purchase.id } : {}),
      ...(!deleting ? purchase ? { note, ...(parts.length ? { components: parts.map(p => ({ service_id: p.service_id, remaining: Number(p.remaining) })) } : { remaining: Number(remaining) }) } : { customer_name: name, customer_phone: phone } : {}) }
    if (await onAction(action, payload, [], { expectedRevision: revision })) onClose()
  }
  return <div className="live-tour-modal-backdrop"><section ref={ref} tabIndex="-1" className="live-tour-modal tour-booking-dialog" role="dialog" aria-modal="true" aria-label={title}>
    <div className="live-tour-modal-head"><strong>{title} · {customer.name}</strong><button type="button" className="secondary-button" disabled={busy} onClick={onClose}>Đóng</button></div>
    {error && <p role="alert" className="error-box">{error}</p>}
    <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
      {purchase && <p className="wide">{purchase.combo_name} · Đã dùng {purchase.used || 0} vé</p>}
      {deleting ? <p className="wide">Mục này sẽ được gỡ khỏi danh sách sử dụng. Hóa đơn và lịch sử đã phát sinh vẫn được giữ để đối chiếu.</p> : purchase ? <>
        {parts.length ? parts.map((part, index) => <label className="live-tour-field wide" key={part.service_id}><span>{part.service_name || part.name || part.service_id} · Đã dùng {part.used}</span><input required type="number" min="0" max="100000" value={part.remaining} onChange={e => setParts(rows => rows.map((r,i) => i === index ? { ...r, remaining: e.target.value } : r))}/></label>) : <label className="live-tour-field wide"><span>Số vé còn lại</span><input type="number" required min="0" max="100000" value={remaining} onChange={e => setRemaining(e.target.value)}/></label>}
        <label className="live-tour-field wide"><span>Ghi chú</span><textarea maxLength={2000} value={note} onChange={e => setNote(e.target.value)}/></label>
      </> : <><label className="live-tour-field"><span>Tên khách hàng</span><input required maxLength={150} value={name} onChange={e => setName(e.target.value)}/></label><label className="live-tour-field"><span>Điện thoại</span><input maxLength={30} value={phone} onChange={e => setPhone(e.target.value)}/></label></>}
      <label className="live-tour-field wide"><span>Lý do *</span><textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)}/></label>
      <button type="submit" className={deleting ? 'secondary-button danger-button' : 'primary-button'} disabled={!reason.trim()}>{deleting ? 'Xác nhận xóa' : 'Lưu thay đổi'}</button>
    </fieldset></form>
  </section></div>
}
