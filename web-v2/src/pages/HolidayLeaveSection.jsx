import { useCallback, useEffect, useRef, useState } from 'react'
import { CalendarDays, RefreshCw } from 'lucide-react'
import VeraDateInput from '../components/VeraDateInput'
import VeraDateTimeInput from '../components/VeraDateTimeInput'
import { alertDialog, confirmDialog } from '../lib/systemDialogs'
import { veraApi } from '../lib/api'
import { formatVeraDate } from '../lib/veraDate'
import { holidayPayload, holidayPeriodsLabel, vietnamToday } from '../lib/holidayLeave'
import './HolidayLeaveSection.css'

const emptyForm = () => {
  const today = vietnamToday()
  return { scope: 'all', departments: [], employees: [], mode: 'day', day: today,
    dates: [], dateFrom: today, dateTo: today, startsAt: `${today}T09:00`, endsAt: `${today}T17:00`, note: '' }
}
const toggle = (values, value) => values.includes(value) ? values.filter(item => item !== value) : [...values, value]
const scopeLabels = { all: 'Toàn bộ nhân viên', departments: 'Theo bộ phận', employees: 'Theo nhân viên' }

export default function HolidayLeaveSection() {
  const [form, setForm] = useState(emptyForm)
  const [data, setData] = useState({ registrations: [], employees: [], departments: [], can_register: false, can_cancel: false })
  const [busy, setBusy] = useState(false)
  const [loading, setLoading] = useState(false)
  const [search, setSearch] = useState('')
  const [newDate, setNewDate] = useState('')
  const [dateValid, setDateValid] = useState(true)
  const [filter, setFilter] = useState(() => {
    const today = vietnamToday(); const [year, month] = today.split('-').map(Number)
    return { start: `${today.slice(0, 7)}-01`, end: new Date(Date.UTC(year, month, 0)).toISOString().slice(0, 10) }
  })
  const requestId = useRef(crypto.randomUUID())
  const sequence = useRef(0)
  const formRef = useRef(null)
  const load = useCallback(async (range = filter) => {
    const current = ++sequence.current
    if (!range.start || !range.end) return
    setLoading(true)
    try {
      const result = await veraApi.holidayLeave(range.start, range.end)
      if (current === sequence.current) setData(result)
    } catch (error) {
      if (current === sequence.current) await alertDialog(error.message, { kind: 'error' })
    } finally { if (current === sequence.current) setLoading(false) }
  }, [filter])
  useEffect(() => { void load(); return () => { sequence.current += 1 } }, [load])
  const change = (field, value) => {
    requestId.current = crypto.randomUUID()
    setForm(current => ({ ...current, [field]: value }))
  }
  const selected = data.employees.filter(employee => form.scope === 'all'
    || (form.scope === 'departments' ? form.departments.includes(employee.department) : form.employees.includes(employee.username)))
  const register = async event => {
    event.preventDefault()
    if (!formRef.current.reportValidity()) return
    if (!selected.length || (form.mode === 'dates' && !form.dates.length)) {
      await alertDialog('Chọn nhân viên và ngày nghỉ trước khi đăng ký.', { kind: 'error' }); return
    }
    if (form.mode === 'dates' && newDate) {
      await alertDialog('Bấm Thêm ngày để đưa ngày đang nhập vào danh sách nghỉ.', { kind: 'warning' }); return
    }
    if (!await confirmDialog(`Đăng ký nghỉ lễ “${form.note.trim()}” cho ${selected.length} nhân viên?`)) return
    setBusy(true)
    try {
      const result = await veraApi.registerHolidayLeave(holidayPayload(form, requestId.current))
      await alertDialog(result.message, { kind: 'success' })
      const days = form.mode === 'hours' ? [form.startsAt.slice(0,10), form.endsAt.slice(0,10)]
        : form.mode === 'range' ? [form.dateFrom, form.dateTo] : form.mode === 'day' ? [form.day] : [...form.dates].sort()
      const range = { start: days[0], end: days[days.length-1] }
      change('note', '')
      setFilter(range)
      await load(range)
    } catch (error) { await alertDialog(error.message, { kind: 'error' }) }
    finally { setBusy(false) }
  }
  const cancel = async row => {
    if (!await confirmDialog(`Huỷ lịch nghỉ lễ “${row.note}” cho ${row.employees?.length || 0} nhân viên?`)) return
    setBusy(true)
    try {
      const result = await veraApi.cancelHolidayLeave(row.id, row.revision)
      await alertDialog(result.message, { kind: 'success' }); await load()
    } catch (error) { await alertDialog(error.message, { kind: 'error' }) }
    finally { setBusy(false) }
  }
  return <section className="panel holiday-leave-section" aria-label="Đăng ký nghỉ lễ">
    <div className="holiday-leave-heading"><h2><CalendarDays size={20} /> ĐĂNG KÝ NGHỈ LỄ</h2>
      <button type="button" className="secondary-button" onClick={() => { void load() }} disabled={busy || loading}><RefreshCw size={15} /> Làm mới lịch nghỉ lễ</button></div>
    {data.can_register && <form ref={formRef} onSubmit={register}>
      <fieldset disabled={busy || loading} className="holiday-leave-fields">
        <div className="form-grid">
          <label>Phạm vi<select value={form.scope} onChange={event => change('scope', event.target.value)}>
            {Object.entries(scopeLabels).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
          </select></label>
          <label>Thời gian nghỉ<select value={form.mode} onChange={event => change('mode', event.target.value)}>
            <option value="day">Một ngày</option><option value="dates">Nhiều ngày tự chọn</option>
            <option value="range">Từ ngày đến ngày</option><option value="hours">Từ giờ đến giờ</option>
          </select></label>
          <label>Tên lễ / ghi chú<input value={form.note} required maxLength={1000} onChange={event => change('note', event.target.value)} /></label>
        </div>
        {form.scope === 'departments' && <div className="holiday-leave-selector" role="group" aria-label="Chọn bộ phận">
          {data.departments.map(department => <label key={department.code}><input type="checkbox" checked={form.departments.includes(department.code)} onChange={() => change('departments', toggle(form.departments, department.code))} />{department.name}</label>)}
        </div>}
        {form.scope === 'employees' && <div className="holiday-leave-selector">
          <label>Tìm nhân viên<input value={search} onChange={event => setSearch(event.target.value)} /></label>
          <div className="holiday-leave-people" role="group" aria-label="Chọn nhân viên">
            {data.employees.filter(employee => `${employee.username} ${employee.full_name}`.toLocaleLowerCase('vi').includes(search.toLocaleLowerCase('vi'))).map(employee => <label key={employee.username}><input type="checkbox" checked={form.employees.includes(employee.username)} onChange={() => change('employees', toggle(form.employees, employee.username))} />{employee.username} · {employee.full_name}</label>)}
          </div>
        </div>}
        <div className="form-grid">
          {form.mode === 'day' && <label>Ngày nghỉ<VeraDateInput value={form.day} required aria-label="Ngày nghỉ lễ" onChange={event => change('day', event.target.value)} /></label>}
          {form.mode === 'range' && <><label>Từ ngày<VeraDateInput value={form.dateFrom} required aria-label="Nghỉ lễ từ ngày" onChange={event => change('dateFrom', event.target.value)} /></label><label>Đến ngày<VeraDateInput value={form.dateTo} min={form.dateFrom} required aria-label="Nghỉ lễ đến ngày" onChange={event => change('dateTo', event.target.value)} /></label></>}
          {form.mode === 'hours' && <><label>Từ ngày giờ<VeraDateTimeInput value={form.startsAt} required aria-label="Nghỉ lễ bắt đầu" onChange={event => change('startsAt', event.target.value)} /></label><label>Đến ngày giờ<VeraDateTimeInput value={form.endsAt} required aria-label="Nghỉ lễ kết thúc" onChange={event => change('endsAt', event.target.value)} /></label></>}
          {form.mode === 'dates' && <div><label>Thêm ngày nghỉ<VeraDateInput value={newDate} aria-label="Ngày nghỉ lễ tự chọn" onDraftValidity={setDateValid} onChange={event => setNewDate(event.target.value)} /></label><button type="button" className="secondary-button" disabled={!newDate || !dateValid} onClick={() => { change('dates', [...new Set([...form.dates, newDate])].sort()); setNewDate('') }}>Thêm ngày</button>
            <div className="holiday-date-list">{form.dates.map(day => <button type="button" className="secondary-button" key={day} aria-label={`Bỏ ngày ${formatVeraDate(day)}`} onClick={() => change('dates', form.dates.filter(value => value !== day))}>{formatVeraDate(day)} ×</button>)}</div></div>}
        </div>
        <p>Áp dụng cho <strong>{selected.length}</strong> nhân viên đang làm việc hoặc thử việc. Danh sách được chốt khi đăng ký.</p>
        <button className="primary-button" type="submit" disabled={!selected.length}>Đăng ký nghỉ lễ</button>
      </fieldset>
    </form>}
    {!loading && !data.can_register && <p>Bạn chưa được cấp quyền đăng ký nghỉ lễ. Lịch bên dưới hiển thị các kỳ nghỉ áp dụng cho bạn.</p>}
    <h3>LỊCH NGHỈ LỄ ĐÃ ĐĂNG KÝ</h3>
    <div className="form-grid"><label>Xem từ ngày<VeraDateInput value={filter.start} aria-label="Lọc nghỉ lễ từ ngày" onChange={event => setFilter(current => ({ ...current, start: event.target.value }))} /></label><label>Đến ngày<VeraDateInput value={filter.end} min={filter.start} aria-label="Lọc nghỉ lễ đến ngày" onChange={event => setFilter(current => ({ ...current, end: event.target.value }))} /></label></div>
    <div className="table-scroll"><table><thead><tr><th>Tên lễ / ghi chú</th><th>Phạm vi</th><th>Thời gian</th><th>Nhân viên</th><th>Trạng thái</th><th>Thao tác</th></tr></thead>
      <tbody>{data.registrations.map(row => <tr key={row.id}><td>{row.note}</td><td>{scopeLabels[row.scope]}</td><td>{holidayPeriodsLabel(row)}</td><td><details><summary>{row.employees?.length || 0} nhân viên</summary>{(row.employees || []).map(employee => <div key={employee.username}>{employee.username}</div>)}</details></td><td>{row.cancelled_at ? 'Đã huỷ' : 'Đã đăng ký'}</td><td>{data.can_cancel && !row.cancelled_at && <button type="button" className="danger-button" disabled={busy || loading} onClick={() => cancel(row)}>Huỷ đăng ký</button>}</td></tr>)}</tbody></table></div>
    {!loading && !data.registrations.length && <p>Chưa có lịch nghỉ lễ trong khoảng ngày đang xem.</p>}
  </section>
}
