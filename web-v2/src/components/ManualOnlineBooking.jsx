import { useEffect, useRef, useState } from 'react'
import EmployeeProfileModal from './EmployeeProfileModal'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import VeraDateInput from './VeraDateInput'
import { veraApi } from '../lib/api'
import { bookingDateRange } from '../lib/bookingDateRange'
import { catalogIsAvailable } from '../lib/serviceCatalog'

export default function ManualOnlineBooking({ services = [], booking, onClose, onSaved }) {
  const [draft, setDraft] = useState({ service: '', guests: 1, appointment_date: bookingDateRange('today').date_from, appointment_time: '', customer_name: '', phone: '', requested_staff: '', message: '', ...(booking ? Object.fromEntries(['service', 'guests', 'appointment_date', 'appointment_time', 'customer_name', 'phone', 'requested_staff', 'message'].map(key => [key, booking[key] ?? ''])) : {}) })
  const [staff, setStaff] = useState([])
  const [staffError, setStaffError] = useState('')
  const [staffLoading, setStaffLoading] = useState(true)
  useEffect(() => {
    let active = true
    veraApi.onlineBookingStaff().then(result => { if (active) setStaff(result.employees || []) }).catch(err => { if (active) setStaffError(err.message) }).finally(() => { if (active) setStaffLoading(false) })
    return () => { active = false }
  }, [])
  const [query, setQuery] = useState('')
  const [customers, setCustomers] = useState([])
  const [lookupError, setLookupError] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const eventId = useRef(null)
  const set = (key, value) => setDraft(old => ({ ...old, [key]: value }))
  useEffect(() => {
    let active = true
    setCustomers([]); setLookupError('')
    if (!query.trim()) return undefined
    const timer = setTimeout(() => {
      veraApi.liveTourCollection('customers', { search: query.trim(), page_size: 20 }).then(result => {
        if (active) setCustomers(result.data?.customers || [])
      }).catch(err => { if (active) setLookupError(err.message) })
    }, 250)
    return () => { active = false; clearTimeout(timer) }
  }, [query])
  const choose = id => {
    const customer = customers.find(row => row.id === id)
    if (customer) { setDraft(old => ({ ...old, customer_name: customer.name || '', phone: customer.phone || '' })); setQuery('') }
  }
  const save = async event => {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true; setBusy(true); setError('')
    eventId.current ||= crypto.randomUUID()
    try {
      const payload = { ...draft, event_id: eventId.current, kind: 'booking' }
      if (booking) await veraApi.updateOnlineBooking(booking.id, { status: booking.status, note: booking.note || '', revision: booking.revision, booking: payload })
      else await veraApi.createOnlineBooking(payload)
      window.dispatchEvent(new Event('vera-online-bookings-changed'))
      onSaved()
    } catch (err) { setError(err.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  const catalog = services.filter(row => catalogIsAvailable(row)).sort((a, b) => Number(b.price || 0) - Number(a.price || 0))
  const serviceOptions = catalog.map(row => {
    const label = `${row.name}${row.duration ? ` · ${row.duration} phút` : ''}${row.price != null ? ` · ${Number(row.price).toLocaleString('vi-VN')}đ` : ''}`
    return { value: label, label }
  })
  if (draft.service && !serviceOptions.some(row => row.value === draft.service)) serviceOptions.unshift({ value: draft.service, label: draft.service })
  return <EmployeeProfileModal labelledBy="manual-booking-title" className="upcoming-booking-modal manual-online-booking-modal" busy={busy} onClose={onClose}>
    <header><h2 id="manual-booking-title">ĐẶT LỊCH - BOOKING</h2><button disabled={busy} onClick={onClose}>Đóng</button></header>
    <form className="manual-booking-form" onSubmit={save}>
      <div className="manual-booking-fields">
        <LiveTourSearchSelect className="wide manual-booking-services" label="Dịch vụ" placeholder="Chưa chọn dịch vụ" emptyLabel="Chưa chọn dịch vụ" inlineOptions disabled={busy} value={draft.service} options={serviceOptions} onChange={value => set('service', value)}/>
        <label className="wide">Số khách *<input aria-label="Số khách" type="number" required min="1" max="50" step="1" disabled={busy} value={draft.guests} onChange={event => set('guests', event.target.value === '' ? '' : Number(event.target.value))}/></label>
        <label>Ngày đến *<VeraDateInput aria-label="Ngày đến" required disabled={busy} min={booking ? undefined : bookingDateRange('today').date_from} value={draft.appointment_date} onChange={event => set('appointment_date', event.target.value)}/></label>
        <label>Giờ đến mong muốn *<input aria-label="Giờ đến mong muốn" type="time" step="900" required disabled={busy} value={draft.appointment_time} onChange={event => set('appointment_time', event.target.value)}/></label>
        {['customer_name', 'phone'].map(field => {
          const label = field === 'phone' ? 'Số điện thoại' : 'Tên khách hàng'
          const required = field === 'customer_name'
          return <LiveTourSearchSelect key={field} label={required ? `${label} *` : label} placeholder={`Nhập ${label.toLowerCase()}`} required={required} disabled={busy} value="" searchValue={draft[field]} onSearch={value => { set(field, value); setQuery(value) }} onChange={choose} filterOption={() => true} options={customers.map(row => ({ value: row.id, label: field === 'phone' ? row.phone : row.name, detail: field === 'phone' ? row.name : row.phone }))}/>
        })}
        {lookupError && <p className="wide" role="status">Chưa tra cứu được khách hàng: {lookupError}. Bạn vẫn có thể nhập thông tin khách.</p>}
        <LiveTourSearchSelect className="wide" label="YC nhân viên" placeholder={staffLoading ? 'Đang tải nhân viên…' : 'Tìm và chọn nhân viên đi làm hôm nay'} disabled={busy || staffLoading || Boolean(staffError)} value={draft.requested_staff} onChange={value => set('requested_staff', value)} options={staff}/>
        {staffError && <p className="wide" role="status">Chưa tải được nhân viên: {staffError}</p>}
        <label className="wide">Lời nhắn<textarea rows="2" aria-label="Lời nhắn" maxLength={4000} disabled={busy} value={draft.message} onChange={event => set('message', event.target.value)}/></label>
        {error && <p className="wide" role="alert">{error}</p>}
      </div>
      <div className="online-booking-actions manual-booking-actions"><button type="button" disabled={busy} onClick={onClose}>Đóng</button><button type="submit" disabled={busy || (Boolean(draft.requested_staff) && (staffLoading || Boolean(staffError)))}>{busy ? 'Đang lưu…' : booking ? 'Lưu thay đổi' : 'Lưu lịch đặt Booking'}</button></div>
    </form>
  </EmployeeProfileModal>
}
