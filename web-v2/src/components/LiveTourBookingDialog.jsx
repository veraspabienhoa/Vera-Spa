import { useState } from 'react'
import { flushSync } from 'react-dom'
import { advanceBookingField } from '../lib/advanceBookingField'
import { bookingRoomGroup, bookingRoomState, roomOptionMatches } from '../lib/liveTourRooms'
import { Plus, Trash2 } from 'lucide-react'
import { bookingEmployees, bookingServiceItems, bookingTotal, tourNameKey } from '../lib/liveTourBooking'
import { catalogIsAvailable } from '../lib/serviceCatalog'
import { customerOptionMatches } from '../lib/customerSearch'
import { availableBookingPurchase, comboBookingError, comboBookingItems, customerPurchases, customerTicketLabel, preferredBookingCombo } from '../lib/liveTourComboBooking'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import './LiveTourBookingDialog.css'
import LiveTourTransactionDialog from './LiveTourTransactionDialog'
import LiveTourPageItems from './LiveTourPageItems'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' đ'

function LiveTourMultiBookingDialog({ data, context, canBook, canCustomers, busy, error, onAction, onClose }) {
  const employees = data.state?.employees || []
  const catalog = data.services || []
  const rooms = data.catalogs?.rooms?.length ? data.catalogs.rooms : data.state?.rooms || []
  const eligibleEmployees = bookingEmployees(employees)
  const groupRooms = rooms.filter((item) => bookingRoomGroup(item.name, rooms) === context.roomGroup)
  const blankRow = (usedRooms = []) => {
    const available = bookingRoomState(rooms, data.room_assignments || employees, catalog, '', '', []).options
      .filter((option) => option.group === context.roomGroup && !option.className && !usedRooms.includes(option.value))
    return { employee_id: '', customer_id: '', service_id: '', room: available[0]?.value || groupRooms[0]?.name || '', request: '' }
  }
  const [rows, setRows] = useState(() => [blankRow()])
  const [note, setNote] = useState('')
  const [message, setMessage] = useState('')
  const updateRow = (index, patch) => setRows((current) => current.map((row, rowIndex) => rowIndex === index ? { ...row, ...patch } : row))
  const removeRow = (index) => setRows((current) => current.length === 1 ? current : current.filter((_, rowIndex) => rowIndex !== index))
  const addRow = () => setRows((current) => current.length >= groupRooms.length ? current : [...current, blankRow(current.map((row) => row.room))])
  const submit = async (event) => {
    event.preventDefault(); setMessage('')
    if (rows.some((row) => !row.employee_id || !row.service_id || !row.room)) return setMessage('Mỗi dòng phải chọn nhân viên, dịch vụ và phòng/giường.')
    if (new Set(rows.map((row) => row.employee_id)).size !== rows.length) return setMessage('Một nhân viên không thể xuất hiện ở nhiều dòng booking.')
    if (new Set(rows.map((row) => tourNameKey(row.room))).size !== rows.length) return setMessage('Mỗi nhân viên phải được chọn một giường khác nhau.')
    for (const row of rows) {
      const state = bookingRoomState(rooms, data.room_assignments || employees, catalog, row.employee_id, row.room, [{ service_id: row.service_id, quantity: 1 }])
      if (state.error) return setMessage(state.error)
    }
    const bookings = rows.map((row) => ({
      employee_id: row.employee_id, service_items: [{ service_id: row.service_id, quantity: 1 }], room: row.room,
      request: row.request, note, ...(canCustomers ? { customer_id: row.customer_id || null } : {}),
      start_now: false,
    }))
    const result = await onAction('multi_booking', { bookings }, [])
    if (result) onClose()
  }
  const employeeOptions = eligibleEmployees.map((row) => ({ value: row.id, label: row.name, detail: row.service ? `${row.status} · ${row.room}` : 'Đang rảnh' }))
  const customerOptions = (data.customers || []).map((row) => ({ value: row.id, label: row.name, detail: row.phone, badge: customerTicketLabel(row) }))
  const serviceOptions = catalog.filter((item) => catalogIsAvailable(item)).map((item) => ({ value: item.id, label: item.name, detail: `${item.duration ?? '∞'} phút · ${money(item.price)}` }))
  return <LiveTourTransactionDialog busy={busy} onClose={onClose} className="tour-booking-dialog tour-multi-booking-dialog" title={`Đặt lịch · ${context.roomLabel}`}>
    {(error || message) && <p className="error-box" role="alert">{error || message}</p>}
    <form onSubmit={submit}><fieldset disabled={busy} className="tour-multi-booking-form">
      <div className="tour-multi-booking-rows">{rows.map((row, index) => {
        const roomOptions = bookingRoomState(rooms, data.room_assignments || employees, catalog, row.employee_id, row.room, row.service_id ? [{ service_id: row.service_id, quantity: 1 }] : []).options.filter((option) => option.group === context.roomGroup)
        return <div className="tour-multi-booking-row" key={index}>
          <LiveTourSearchSelect label="Nhân viên *" options={employeeOptions.filter((option) => option.value === row.employee_id || !rows.some((item) => item.employee_id === option.value))} value={row.employee_id} onChange={(value) => updateRow(index, { employee_id: value })} required/>
          {canCustomers && <LiveTourSearchSelect label="Khách hàng" placeholder="Tìm tên hoặc số điện thoại" filterOption={customerOptionMatches} options={customerOptions} value={row.customer_id} onChange={(value) => updateRow(index, { customer_id: value })}/>}
          <LiveTourSearchSelect label="Dịch vụ *" showAllOptions options={serviceOptions} value={row.service_id} onChange={(value) => updateRow(index, { service_id: value })} required/>
          <LiveTourSearchSelect label="Phòng / giường *" showAllOptions filterOption={roomOptionMatches} options={roomOptions} value={row.room} onChange={(value) => updateRow(index, { room: value })} required/>
          <label className="live-tour-field"><span>Yêu cầu</span><select value={row.request} onChange={(event) => updateRow(index, { request: event.target.value })}><option value="">Để trống</option><option value="YC">YC</option></select></label>
          {rows.length > 1 && <button type="button" className="icon-button tour-multi-remove" aria-label={`Xóa dòng ${index + 1}`} onClick={() => removeRow(index)}><Trash2 size={16}/></button>}
        </div>
      })}</div>
      <button type="button" className="secondary-button tour-multi-add" disabled={rows.length >= groupRooms.length} onClick={addRow}><Plus size={15}/> Thêm dòng ({rows.length}/{groupRooms.length})</button>
      <label className="live-tour-field tour-booking-note"><span>Ghi chú</span><textarea value={note} onChange={(event) => setNote(event.target.value)}/></label>
      <div className="wide tour-booking-total"><span>Tiền dịch vụ</span><strong>{money(rows.reduce((total, row) => total + Number(catalog.find((item) => item.id === row.service_id)?.price || 0), 0))}</strong></div>
      <div className="live-tour-modal-actions wide"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button>{canBook && <button type="submit" className="primary-button" value="book">Đặt lịch</button>}</div>
    </fieldset></form>
  </LiveTourTransactionDialog>
}

export default function LiveTourBookingDialog({ data, context, canOperate, canBook, canCustomers, canPayment, busy, error, onAction, onClose, onCheckout }) {
  const employees = [...(data.state?.employees || []), ...(data.retained_assignments || [])]
  const initial = employees.find((row) => row.id === context.employeeId)
  const catalog = data.services || []
  const [employeeId, setEmployeeId] = useState(initial?.id || '')
  const [items, setItems] = useState(() => bookingServiceItems(initial, catalog))
  const [room, setRoom] = useState(initial?.service ? initial.room : '')
  const [request, setRequest] = useState(initial?.service ? initial.request : '')
  const [customerId, setCustomerId] = useState(initial?.service ? initial.customer_id || '' : '')
  const [comboId, setComboId] = useState(initial?.service ? initial.combo_purchase_id || '' : '')
  const [note, setNote] = useState(initial?.service ? initial.note || '' : '')
  const [serviceId, setServiceId] = useState('')
  const [completed, setCompleted] = useState(null)
  const [message, setMessage] = useState('')
  const employee = employees.find((row) => row.id === employeeId)
  const rooms = data.catalogs?.rooms?.length ? data.catalogs.rooms : data.state?.rooms || []
  const roomState = bookingRoomState(rooms, data.room_assignments || employees, catalog, employeeId, room, items)
  const editing = Boolean(employee?.service)
  const doing = ['dang thuc hien', 'dang su dung'].includes(tourNameKey(employee?.status))
  const selectedCustomer = (data.customers || []).find((row) => row.id === customerId)
  const purchases = customerPurchases(selectedCustomer).map((purchase) => availableBookingPurchase(purchase, employee ? [employee] : []))
  const selectedCombo = purchases.find((purchase) => purchase.id === comboId)
  const comboError = canCustomers && comboId ? (selectedCombo ? comboBookingError(selectedCombo, items, catalog) : 'Không tìm thấy combo đã mua. Hãy chọn lại khách hàng hoặc combo.') : ''
  const selectCustomer = (id) => {
    const customer = (data.customers || []).find((row) => row.id === id)
    const purchase = preferredBookingCombo(customer, catalog)
    setCustomerId(id); setComboId(purchase?.id || ''); setMessage(''); setServiceId('')
    if (purchase || comboId) setItems(comboBookingItems(purchase, catalog))
  }
  const selectCombo = (id) => {
    setComboId(id); setMessage(''); setServiceId('')
    if (id) setItems(comboBookingItems(purchases.find((purchase) => purchase.id === id), catalog))
  }
  const bookingPayload = () => ({
    employee_id: employeeId, service_items: items, room, request, note,
    ...(canCustomers ? { customer_id: customerId || null, customer_name: selectedCustomer?.name || '', customer_phone: selectedCustomer?.phone || '', combo_purchase_id: comboId || '' } : {}),
  })
  const selectEmployee = (id) => {
    const worker = employees.find((row) => row.id === id)
    setEmployeeId(id); setItems(bookingServiceItems(worker, catalog)); setServiceId('')
    setRoom(worker?.service ? worker.room : ''); setRequest(worker?.service ? worker.request : '')
    setCustomerId(worker?.service ? worker.customer_id || '' : ''); setNote(worker?.service ? worker.note || '' : '')
    setComboId(worker?.service ? worker.combo_purchase_id || '' : ''); setMessage('')
  }
  const submit = async (event) => {
    event.preventDefault(); setMessage('')
    if (roomState.error || comboError) { setMessage(roomState.error || comboError); return }
    if (items.some((row) => !Number.isInteger(Number(row.quantity)) || Number(row.quantity) < 1 || Number(row.quantity) > 30)) { setMessage('Số lượng mỗi dịch vụ phải từ 1 đến 30.'); return }
    if (!employeeId || !room || !items.length) { setMessage('Hãy chọn nhân viên, ít nhất một dịch vụ và phòng/giường.'); return }
    const result = await onAction(editing ? 'update_booking' : 'booking', {
      ...bookingPayload(), start_now: false,
    }, [])
    if (result) onClose()
  }
  const finish = async () => {
    setMessage('')
    const changed = JSON.stringify(items) !== JSON.stringify(bookingServiceItems(employee, catalog))
      || room !== employee.room || request !== (employee.request || '') || note !== (employee.note || '')
      || (canCustomers && (customerId !== (employee.customer_id || '') || comboId !== (employee.combo_purchase_id || '')))
    if (changed && roomState.error) { setMessage(roomState.error); return }
    if (changed && comboError) { setMessage(comboError); return }
    if (changed && (!room || !items.length)) { setMessage('Hãy chọn ít nhất một dịch vụ và phòng/giường trước khi hoàn thành.'); return }
    const result = await onAction('finish_to_pending', changed ? bookingPayload() : { employee_id: employeeId }, [])
    if (result) setCompleted(result.result.pending)
  }
  const employeeOptions = bookingEmployees(employees).map((row) => {
    const remaining = row.started_at && row.duration != null ? Math.ceil((new Date(row.started_at).getTime() + Number(row.duration) * 60000 - Date.now()) / 60000) : null
    return { value: row.id, label: row.name, detail: !row.service ? 'Đang rảnh' : `${row.status}${remaining !== null ? ` · ${remaining <= 15 ? 'Sắp xong · ' : ''}Còn ${remaining} phút` : ''} · ${row.room}` }
  })
  const serviceOptions = catalog.filter((item) => catalogIsAvailable(item) && !items.some((row) => row.service_id === item.id)
    && (!selectedCombo?.component_balances || selectedCombo.component_balances.some((part) => part.service_id === item.id && part.remaining > 0)))
    .map((item) => ({ value: item.id, label: item.name, detail: `${item.duration ?? '∞'} phút · ${money(item.price)}` }))
  if (context.roomGroup && !context.employeeId) return <LiveTourMultiBookingDialog data={data} context={context} canOperate={canOperate} canBook={canBook} canCustomers={canCustomers} busy={busy} error={error} onAction={onAction} onClose={onClose}/>
  return <LiveTourTransactionDialog busy={busy} onClose={onClose} className="tour-booking-dialog"
    title={completed ? 'Đã hoàn thành dịch vụ' : editing ? `Booking · ${employee?.name}` : `Đặt lịch${context.roomLabel ? ` · ${context.roomLabel}` : ''}`}>
    {(roomState.error || error || message) && <p className="error-box" role="alert">{roomState.error || error || message}</p>}
    {completed ? <><p>Đã chuyển dịch vụ vào Chờ thanh toán. {employee?.name} đã rảnh để nhận lịch mới.</p><div className="live-tour-modal-actions"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button>{canPayment && <button type="button" className="primary-button" onClick={() => onCheckout(completed)}>Thanh toán</button>}</div></>
      : <form onSubmit={submit}><fieldset disabled={busy} className="tour-booking-form">
        {context.employeeId ? <p className="wide"><strong>Nhân viên: {employee?.name}</strong>{editing && ` · ${employee.status}`}</p> : <div className="wide"><LiveTourSearchSelect advanceOnSelect label="Nhân viên *" options={employeeOptions} value={employeeId} onChange={selectEmployee} required/></div>}
        {canCustomers && <div className="tour-booking-customer"><LiveTourSearchSelect advanceOnSelect label="Khách hàng" placeholder="Tìm tên hoặc số điện thoại" filterOption={customerOptionMatches} options={(data.customers || []).map((row) => ({ value: row.id, label: row.name, detail: row.phone, badge: customerTicketLabel(row) }))} value={customerId} onChange={selectCustomer} disabled={Boolean(editing && employee?.customer_id)}/><small>{customerId ? selectedCustomer?.phone : 'Để trống là Khách lẻ'}</small>{selectedCustomer && <strong className="tour-customer-ticket-count" aria-live="polite">{customerTicketLabel(selectedCustomer)}</strong>}</div>}
        {canCustomers && purchases.length > 0 && <div className="tour-booking-combo">
          <label className="live-tour-field"><span>Combo của khách</span><select data-booking-step value={comboId} onChange={(event) => { const field = event.currentTarget; flushSync(() => selectCombo(field.value)); advanceBookingField(field) }}><option value="">Dịch vụ lẻ · không dùng combo</option>{purchases.map((purchase, index) => <option key={purchase.id} value={purchase.id}>{purchase.combo_name || 'Combo'} · còn {purchase.remaining} vé có thể đặt lịch · #{index + 1}</option>)}</select></label>
          {selectedCombo && <div aria-live="polite"><p><strong>Còn {selectedCombo.remaining} vé</strong> · Giữ vé đến khi thanh toán.</p>{selectedCombo.component_balances ? <LiveTourPageItems items={selectedCombo.component_balances} label="Dịch vụ combo" pageSize={1}>{(part) => <small key={part.service_id}>{catalog.find((service) => service.id === part.service_id)?.name || part.service_name}: còn <strong>{part.remaining}</strong> lượt</small>}</LiveTourPageItems> : <small>Chọn dịch vụ bên dưới để dùng combo vé.</small>}</div>}

          {comboError && <p className="error-box" role="alert">{comboError}</p>}
        </div>}
        <div className="tour-booking-service-picker"><LiveTourSearchSelect advanceOnSelect label="Dịch vụ" showAllOptions clearOnSelect value={serviceId} options={serviceOptions} onChange={(id) => { setServiceId(''); if (id) setItems((current) => [...current, { service_id: id, quantity: 1 }]) }}/></div>
        <div className="tour-booking-items"><LiveTourPageItems items={items} label="Dịch vụ đã chọn">{(row, i) => <div className="tour-booking-item" key={row.service_id}><div><strong>{catalog.find((item) => item.id === row.service_id)?.name || row.service_id}</strong><small>{money(catalog.find((item) => item.id === row.service_id)?.price)}</small></div><label>Số lượng<input type="number" min="1" max="30" required value={row.quantity} onChange={(event) => setItems((current) => current.map((item, index) => index === i ? { ...item, quantity: Number(event.target.value) } : item))}/></label><button type="button" className="icon-button" aria-label={`Bỏ dịch vụ ${i + 1}`} onClick={() => setItems((current) => current.filter((_, index) => index !== i))}><Trash2 size={17}/></button></div>}</LiveTourPageItems>{!items.length && <p><Plus size={14}/> Chọn một hoặc nhiều dịch vụ phía trên.</p>}</div>
        <LiveTourSearchSelect advanceOnSelect invalid={Boolean(roomState.error)} label="Phòng / giường *" value={room} required options={roomState.options} showAllOptions filterOption={roomOptionMatches} onChange={(value) => { setRoom(value); setMessage('') }}/>
        <label className="live-tour-field"><span>Yêu cầu</span><select data-booking-step value={request} disabled={doing} onChange={(event) => { setRequest(event.target.value); advanceBookingField(event.currentTarget) }}><option value="">Để trống</option><option value="YC">YC</option></select></label>
        <label className="live-tour-field tour-booking-note"><span>Ghi chú</span><textarea data-booking-step value={note} onChange={(event) => setNote(event.target.value)}/></label>
        <div className="wide tour-booking-total"><span>Tiền dịch vụ</span><strong>{money(bookingTotal(items, catalog))}</strong></div>
        <div className="live-tour-modal-actions wide"><button type="button" className="secondary-button" onClick={onClose}>Đóng</button>{(editing ? canOperate : canBook) && <><button type="submit" className="primary-button" value="book" disabled={!employeeId || Boolean(comboError || roomState.error)}>{editing ? 'Lưu dịch vụ' : 'Đặt lịch'}</button>{doing && canOperate && <button type="button" className="primary-button" onClick={finish}>Hoàn thành</button>}</>}{canPayment && tourNameKey(employee?.status) === 'cho thanh toan' && <button type="button" className="primary-button" onClick={() => onCheckout(null, employee)}>Thanh toán</button>}</div>
      </fieldset></form>}
  </LiveTourTransactionDialog>
}
