import { useState } from 'react'
import { Plus, Trash2, X } from 'lucide-react'
import { bookingEmployees, bookingServiceItems, bookingTotal, tourNameKey } from '../lib/liveTourBooking'
import { catalogIsAvailable } from '../lib/serviceCatalog'
import { bookingPlaces, isPrivateCatalogService } from '../lib/liveTourAvailability'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import './LiveTourBookingDialog.css'
import useDialogFocus from '../lib/useDialogFocus'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' đ'

export default function LiveTourBookingDialog({ data, context, canOperate, canPayment, busy, error, onAction, onClose, onCheckout, now = Date.now() }) {
  const dialogRef = useDialogFocus(() => { if (!busy) onClose() })
  const employees = [...(data.state?.employees || []), ...(data.retained_assignments || [])]
  const initial = employees.find((row) => row.id === context.employeeId)
  const catalog = data.services || []
  const [employeeId, setEmployeeId] = useState(initial?.id || '')
  const [items, setItems] = useState(() => bookingServiceItems(initial, catalog))
  const [room, setRoom] = useState(initial?.service ? initial.room : '')
  const [request, setRequest] = useState(initial?.service ? initial.request : '')
  const [customerId, setCustomerId] = useState(initial?.service ? initial.customer_id || '' : '')
  const [note, setNote] = useState(initial?.service ? initial.note || '' : '')
  const [serviceId, setServiceId] = useState('')
  const [completed, setCompleted] = useState(null)
  const [message, setMessage] = useState('')
  const employee = employees.find((row) => row.id === employeeId)
  const editing = Boolean(employee?.service)
  const doing = ['dang thuc hien', 'dang su dung'].includes(tourNameKey(employee?.status))
  const selectedCustomer = (data.customers || []).find((row) => row.id === customerId)
  const places = bookingPlaces(data, { employeeId, now, reserve: !doing, privateService: items.some((row) => isPrivateCatalogService(catalog.find((service) => service.id === row.service_id))) })
  const selectedPlace = places.find((place) => place.name === room)
  const bookingPayload = () => ({
    employee_id: employeeId, service_items: items, room, request, note,
    ...(canPayment ? { customer_id: customerId || null, customer_name: selectedCustomer?.name || '', customer_phone: selectedCustomer?.phone || '' } : {}),
  })
  const selectEmployee = (id) => {
    const worker = employees.find((row) => row.id === id)
    setEmployeeId(id); setItems(bookingServiceItems(worker, catalog)); setServiceId('')
    setRoom(worker?.service ? worker.room : ''); setRequest(worker?.service ? worker.request : '')
    setCustomerId(worker?.service ? worker.customer_id || '' : ''); setNote(worker?.service ? worker.note || '' : '')
  }
  const submit = async (event) => {
    event.preventDefault(); setMessage('')
    if (!employeeId || !room || !items.length) { setMessage('Hãy chọn nhân viên, ít nhất một dịch vụ và phòng/giường.'); return }
    if (!selectedPlace) { setMessage('Phòng/giường không còn phù hợp. Hãy chọn lại từ danh sách.'); return }
    const result = await onAction(editing ? 'update_booking' : 'booking', {
      ...bookingPayload(), start_now: event.nativeEvent.submitter?.value === 'start',
    }, [])
    if (result) onClose()
  }
  const finish = async () => {
    setMessage('')
    const changed = JSON.stringify(items) !== JSON.stringify(bookingServiceItems(employee, catalog))
      || room !== employee.room || request !== (employee.request || '') || note !== (employee.note || '')
      || (canPayment && customerId !== (employee.customer_id || ''))
    if (changed && (!selectedPlace || !items.length)) { setMessage('Hãy chọn ít nhất một dịch vụ và phòng/giường phù hợp trước khi hoàn thành.'); return }
    const result = await onAction('finish_to_pending', changed ? bookingPayload() : { employee_id: employeeId }, [])
    if (result) setCompleted(result.result.pending)
  }
  const employeeOptions = bookingEmployees(employees).map((row) => {
    const remaining = row.started_at && row.duration != null ? Math.ceil((new Date(row.started_at).getTime() + Number(row.duration) * 60000 - Date.now()) / 60000) : null
    return { value: row.id, label: row.name, detail: !row.service ? 'Đang rảnh' : `${row.status}${remaining !== null ? ` · ${remaining <= 15 ? 'Sắp xong · ' : ''}Còn ${remaining} phút` : ''} · ${row.room}` }
  })
  const serviceOptions = catalog.filter((item) => catalogIsAvailable(item) && !items.some((row) => row.service_id === item.id)).map((item) => ({ value: item.id, label: item.name, detail: `${item.duration ?? '∞'} phút · ${money(item.price)}` }))
  return <div className="live-tour-modal-backdrop" onClick={() => { if (!busy) onClose() }}><section ref={dialogRef} tabIndex="-1" className="live-tour-modal tour-booking-dialog" role="dialog" aria-modal="true" aria-label={editing ? `Booking · ${employee?.name}` : 'Đặt lịch'} onClick={(event) => event.stopPropagation()}>
    <div className="live-tour-modal-head"><strong>{completed ? 'Đã hoàn thành dịch vụ' : editing ? `Booking · ${employee?.name}` : `Đặt lịch${context.roomLabel ? ` · ${context.roomLabel}` : ''}`}</strong><button className="icon-button" type="button" disabled={busy} aria-label="Đóng" onClick={onClose}><X size={18}/></button></div>
    {(error || message) && <p className="error-box" role="alert">{error || message}</p>}
    {completed ? <><p>Đã chuyển dịch vụ vào Chờ thanh toán. {employee?.name} đã rảnh để nhận lịch mới.</p><div className="live-tour-modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button>{canPayment && <button type="button" className="primary-button" onClick={() => onCheckout(completed)}>Thanh toán</button>}</div></>
      : <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
        {context.employeeId ? <p className="wide"><strong>Nhân viên: {employee?.name}</strong>{editing && ` · ${employee.status}`}</p> : <div className="wide"><LiveTourSearchSelect label="Nhân viên *" options={employeeOptions} value={employeeId} onChange={selectEmployee} required/></div>}
        {canPayment && <div className="wide"><LiveTourSearchSelect label="Khách hàng" placeholder="Tìm khách hàng · để trống là Khách lẻ" options={(data.customers || []).map((row) => ({ value: row.id, label: row.name, detail: row.phone }))} value={customerId} onChange={setCustomerId} disabled={Boolean(editing && employee?.customer_id)}/><small>{customerId ? selectedCustomer?.phone : 'Khách lẻ'}</small></div>}
        <div className="wide"><LiveTourSearchSelect label="Dịch vụ" clearOnSelect value={serviceId} options={serviceOptions} onChange={(id) => { setServiceId(''); if (id) setItems((current) => [...current, { service_id: id, quantity: 1 }]) }}/></div>
        <div className="wide tour-booking-items">{items.map((row, i) => <div className="tour-booking-item" key={row.service_id}><div><strong>{catalog.find((item) => item.id === row.service_id)?.name || row.service_id}</strong><small>{money(catalog.find((item) => item.id === row.service_id)?.price)}</small></div><label>Số lượng<input type="number" min="1" max="30" required value={row.quantity} onChange={(event) => setItems((current) => current.map((item, index) => index === i ? { ...item, quantity: Number(event.target.value) } : item))}/></label><button type="button" className="icon-button" aria-label={`Bỏ dịch vụ ${i + 1}`} onClick={() => setItems((current) => current.filter((_, index) => index !== i))}><Trash2 size={17}/></button></div>)}{!items.length && <p><Plus size={14}/> Chọn một hoặc nhiều dịch vụ phía trên.</p>}</div>
        <LiveTourSearchSelect label="Phòng / giường *" value={room} required options={places.map((row) => ({ value: row.name, label: row.name, detail: [row.area_name, row.notice].filter(Boolean).join(' · ') }))} onChange={setRoom}/>
        <label className="live-tour-field"><span>Yêu cầu</span><select value={request} disabled={doing} onChange={(event) => setRequest(event.target.value)}><option value="">Để trống</option><option value="YC">YC</option></select></label>
        {selectedPlace?.notice && <p className="wide setup-note">{selectedPlace.notice} Chỉ Thực hiện sau khi phiên trước hoàn thành.</p>}
        {room && !selectedPlace && <p className="wide error-box">Phòng/giường {room} không còn phù hợp; hãy chọn lại từ danh sách.</p>}
        <label className="live-tour-field wide"><span>Ghi chú</span><textarea value={note} onChange={(event) => setNote(event.target.value)}/></label>
        <div className="wide tour-booking-total"><span>Tiền dịch vụ</span><strong>{money(bookingTotal(items, catalog))}</strong></div>
        <div className="live-tour-modal-actions wide"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button>{canOperate && <><button type="submit" className="secondary-button" value="book" disabled={!employeeId || !selectedPlace}>{editing ? 'Lưu dịch vụ' : 'Đặt lịch'}</button>{!doing && <button type="submit" className="primary-button" value="start" disabled={!employeeId || !selectedPlace?.can_start}>Thực hiện</button>}{doing && <button type="button" className="primary-button" onClick={finish}>Hoàn thành</button>}</>}{canPayment && tourNameKey(employee?.status) === 'cho thanh toan' && <button type="button" className="primary-button" onClick={() => onCheckout(null, employee)}>Thanh toán</button>}</div>
      </fieldset></form>}
  </section></div>
}
