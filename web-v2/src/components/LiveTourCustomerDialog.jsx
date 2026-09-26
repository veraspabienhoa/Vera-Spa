import StableFeedback from './StableFeedback'
import UiCustomText from './UiCustomText'
import { useState } from 'react'
import useDialogFocus from '../lib/useDialogFocus'
import './LiveTourBookingDialog.css'
export default function LiveTourCustomerDialog({ context, busy, error, onAction, onClose, comboCatalog = [] }) {
  const { customer, purchase, mode, revision } = context
  const deleting = mode === 'delete'
  const ref = useDialogFocus(() => { if (!busy) onClose() })
  const [name, setName] = useState(customer.name || '')
  const [phone, setPhone] = useState(customer.phone || '')
  const [remaining, setRemaining] = useState(purchase?.remaining ?? 0)
  const [comboId, setComboId] = useState(purchase?.combo_id || '')
  const [parts, setParts] = useState(purchase?.component_balances?.map(p => ({ ...p })) || [])
  const [note, setNote] = useState(purchase?.note || '')
  const [reason, setReason] = useState('')
  const title = `${deleting ? 'Xóa' : 'Sửa'} ${purchase ? 'combo của khách' : 'khách hàng'}`
  const submit = async e => {
    e.preventDefault()
    const action = purchase ? `customer_combo_${deleting ? 'delete' : 'update'}` : deleting ? 'customer_delete' : 'customer_upsert'
    const payload = { customer_id: customer.id, reason: reason.trim(), ...(purchase ? { purchase_id: purchase.id, ...(comboId ? { combo_id: comboId } : {}) } : {}),
      ...(!deleting ? purchase ? { note, ...(parts.length ? { components: parts.map(p => ({ service_id: p.service_id, remaining: Number(p.remaining) })) } : { remaining: Number(remaining) }) } : { customer_name: name, customer_phone: phone } : {}) }
    if (await onAction(action, payload, [], { expectedRevision: revision })) onClose()
  }
  return <div className="live-tour-modal-backdrop"><section data-ui-key="u-27e85fc9ad0d" ref={ref} tabIndex="-1" className="live-tour-modal tour-booking-dialog" role="dialog" aria-modal="true" aria-label={title}>
    <div className="live-tour-modal-head"><strong>{title} · {customer.name}</strong><button data-ui-key="u-f227e0371e42" data-ui-label-default="Đóng" type="button" className="secondary-button" disabled={busy} onClick={onClose}><UiCustomText uiKey="u-f227e0371e42">Đóng</UiCustomText></button></div>
    <StableFeedback>{error && <p role="alert" className="error-box">{error}</p>}</StableFeedback>
    <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
      {purchase && <p className="wide">{purchase.combo_name} · Đã dùng {purchase.used || 0} vé</p>}
      {deleting ? <p className="wide">Mục này sẽ được gỡ khỏi danh sách sử dụng. Hóa đơn và lịch sử đã phát sinh vẫn được giữ để đối chiếu.</p> : purchase ? <>
        <label className="live-tour-field wide"><span>Loại combo</span><select value={comboId} disabled={(purchase.used || 0) > 0} onChange={e => {
          const nextId = e.target.value
          const next = comboCatalog.find(item => String(item.id) === nextId)
          setComboId(nextId)
          if (!next || nextId === String(purchase.combo_id || '')) {
            setRemaining(purchase.remaining ?? 0)
            setParts(purchase?.component_balances?.map(part => ({ ...part })) || [])
          } else if (next.components?.length) {
            setParts(next.components.map(part => ({ service_id: part.service_id, service_name: part.service_name, used: 0, remaining: part.quantity })))
          } else {
            setParts([])
            setRemaining(next.tickets ?? 0)
          }
        }}><option value={purchase.combo_id || ''}>{purchase.combo_name || 'Combo hiện tại'}</option>{comboCatalog.filter(item => String(item.id) !== String(purchase.combo_id || '')).map(item => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        {(purchase.used || 0) > 0 && <small className="wide">Combo đã phát sinh lượt sử dụng nên chỉ có thể sửa số vé còn lại.</small>}
        {parts.length ? parts.map((part, index) => <label className="live-tour-field wide" key={part.service_id}><span>{part.service_name || part.name || part.service_id} · Đã dùng {part.used}</span><input required type="number" min="0" max="100000" value={part.remaining} onChange={e => setParts(rows => rows.map((r,i) => i === index ? { ...r, remaining: e.target.value } : r))}/></label>) : <label className="live-tour-field wide"><span>Số vé còn lại</span><input type="number" required min="0" max="100000" value={remaining} onChange={e => setRemaining(e.target.value)}/></label>}
        <label className="live-tour-field wide"><span>Ghi chú</span><textarea maxLength={2000} value={note} onChange={e => setNote(e.target.value)}/></label>
      </> : <><label className="live-tour-field"><span>Tên khách hàng</span><input required maxLength={150} value={name} onChange={e => setName(e.target.value)}/></label><label className="live-tour-field"><span>Điện thoại</span><input maxLength={30} value={phone} onChange={e => setPhone(e.target.value)}/></label></>}
      <label className="live-tour-field wide"><span>Lý do *</span><textarea required maxLength={1000} value={reason} onChange={e => setReason(e.target.value)}/></label>
      <button data-ui-key="u-04f2587aae79" type="submit" className={deleting ? 'secondary-button danger-button' : 'primary-button'} disabled={!reason.trim()}>{deleting ? 'Xác nhận xóa' : 'Lưu thay đổi'}</button>
    </fieldset></form>
  </section></div>
}
