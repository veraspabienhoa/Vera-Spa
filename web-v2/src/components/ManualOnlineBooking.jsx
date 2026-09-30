import { useEffect, useRef, useState } from 'react'
import EmployeeProfileModal from './EmployeeProfileModal'
import LiveTourSearchSelect from './LiveTourSearchSelect'
import VeraDateInput from './VeraDateInput'
import { veraApi } from '../lib/api'
import { bookingDateRange } from '../lib/bookingDateRange'
import { catalogIsAvailable } from '../lib/serviceCatalog'

export default function ManualOnlineBooking({ services, onClose, onSaved }) {
  const [draft, setDraft] = useState({ service: '', guests: 1, appointment_date: bookingDateRange('today').date_from, appointment_time: '', customer_name: '', phone: '', message: '' })
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
      await veraApi.createOnlineBooking({ ...draft, event_id: eventId.current, kind: 'booking' })
      window.dispatchEvent(new Event('vera-online-bookings-changed'))
      onSaved()
    } catch (err) { setError(err.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  const catalog = services.filter(row => catalogIsAvailable(row))
  return <EmployeeProfileModal labelledBy="manual-booking-title" className="upcoming-booking-modal" busy={busy} onClose={onClose}>
    <header><h2 id="manual-booking-title">ĐẶT LỊCH - BOOKING</h2><button disabled={busy} onClick={onClose}>Đóng</button></header>
    <p>Nhập thông tin khách mới hoặc tìm khách đã có bằng tên hay số điện thoại.</p>
    <form className="manual-booking-form" onSubmit={save}>
      <label className="wide">Dịch vụ *<select aria-label="Dịch vụ" required disabled={busy} value={draft.service} onChange={event => set('service', event.target.value)}>
        <option value="">Chọn dịch vụ</option>{catalog.map(row => {
          const label = `${row.name}${row.duration ? ` · ${row.duration} phút` : ''}${row.price != null ? ` · ${Number(row.price).toLocaleString('vi-VN')}đ` : ''}`
          return <option key={row.id} value={label}>{label}</option>
        })}
      </select></label>
      <label className="wide">Số khách *<input aria-label="Số khách" type="number" required min="1" max="50" step="1" disabled={busy} value={draft.guests} onChange={event => set('guests', event.target.value === '' ? '' : Number(event.target.value))}/></label>
      <label>Ngày đến *<VeraDateInput aria-label="Ngày đến" required disabled={busy} min={bookingDateRange('today').date_from} value={draft.appointment_date} onChange={event => set('appointment_date', event.target.value)}/></label>
      <label>Giờ đến mong muốn *<input aria-label="Giờ đến mong muốn" type="time" required disabled={busy} value={draft.appointment_time} onChange={event => set('appointment_time', event.target.value)}/></label>
      {['customer_name', 'phone'].map(field => {
        const label = field === 'phone' ? 'Số điện thoại' : 'Tên khách hàng'
        const required = field === 'customer_name'
        return <LiveTourSearchSelect key={field} label={required ? `${label} *` : label} placeholder={`Nhập ${label.toLowerCase()}`} required={required} disabled={busy} value="" searchValue={draft[field]} onSearch={value => { set(field, value); if (field === 'customer_name') setQuery(value) }} onChange={choose} filterOption={() => true} options={customers.map(row => ({ value: row.id, label: field === 'phone' ? row.phone : row.name, detail: field === 'phone' ? row.name : row.phone }))}/>
      })}
      {lookupError && <p className="wide" role="status">Chưa tra cứu được khách hàng: {lookupError}. Bạn vẫn có thể nhập thông tin khách.</p>}
      <label className="wide">Lời nhắn<textarea aria-label="Lời nhắn" maxLength={4000} disabled={busy} value={draft.message} onChange={event => set('message', event.target.value)}/></label>
      {error && <p className="wide" role="alert">{error}</p>}
      <div className="online-booking-actions wide"><button type="button" disabled={busy} onClick={onClose}>Đóng</button><button type="submit" disabled={busy || !catalog.length}>{busy ? 'Đang lưu…' : 'Lưu lịch đặt Booking'}</button></div>
    </form>
  </EmployeeProfileModal>
}
