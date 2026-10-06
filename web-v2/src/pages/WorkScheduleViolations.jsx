import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import VeraDateInput from '../components/VeraDateInput'
import VeraMoneyInput from '../components/VeraMoneyInput'
import { veraApi } from '../lib/api'
import { formatVeraDate } from '../lib/veraDate'
import { searchTextMatches } from '../lib/searchText'
import './WorkScheduleViolations.css'

import { vietnamToday, violationMonthRange, useViolationRecords } from '../lib/workScheduleViolations'

const money = value => `${Number(value || 0).toLocaleString('vi-VN')}đ`
const userKey = value => String(value || '').trim().toLowerCase()

export default function WorkScheduleViolations({ user, employees, request, revision, onSaved }) {
  const today = vietnamToday()
  const thisMonth = today.slice(0, 7)
  const [year, month] = thisMonth.split('-').map(Number)
  const lastMonth = month === 1 ? `${year - 1}-12` : `${year}-${String(month - 1).padStart(2, '0')}`
  const [period, setPeriod] = useState('current')
  const [customStart, setCustomStart] = useState(`${thisMonth}-01`)
  const [customEnd, setCustomEnd] = useState(today)
  const range = period === 'custom' ? { start: customStart, end: customEnd } : violationMonthRange(period === 'previous' ? lastMonth : thisMonth)
  const state = useViolationRecords(range.start, range.end, revision)
  const [search, setSearch] = useState('')
  const [filterDate, setFilterDate] = useState('')
  const [open, setOpen] = useState(false)
  const [form, setForm] = useState({ employee: '', date: today, reason: '', amount: '', detail: '' })
  const [reasons, setReasons] = useState([])
  const [reasonLoading, setReasonLoading] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const [saving, setSaving] = useState(false)
  const submitting = useRef(false)
  const dialogRef = useRef(null)
  const canEnter = ['admin', 'quanly'].includes(String(user?.role || '').toLowerCase())
  const canViewPenalty = user?.role === 'admin' || user?.permissions?.employee_penalty_view === true
  const employeeMap = useMemo(() => new Map(employees.map(item => [userKey(item.username), item])), [employees])
  const name = employee => employee.system_name || employee.full_name || employee.name || employee.username
  const rows = state.records.filter(item => {
    const employee = employeeMap.get(userKey(item.employee_name))
    return employee && (!filterDate || item.leave_date === filterDate) && searchTextMatches([name(employee), item.employee_name], search)
  })
  const selectedReason = reasons.find(item => item.name === form.reason)

  useEffect(() => {
    if (!open) return
    const controller = new AbortController()
    setReasons([]); setReasonLoading(true); setError('')
    request(`/v2/leave/reason-groups?date=${encodeURIComponent(form.date)}`, { signal: controller.signal }).then(result => {
      if (!controller.signal.aborted) setReasons(result.violations || [])
    }).catch(error => { if (!controller.signal.aborted) setError(error.message) })
      .finally(() => { if (!controller.signal.aborted) setReasonLoading(false) })
    return () => controller.abort()
  }, [open, form.date, request])

  useEffect(() => {
    if (!open) return
    const previous = document.activeElement
    dialogRef.current?.showModal()
    dialogRef.current?.querySelector('select')?.focus()
    return () => previous?.focus?.()
  }, [open])

  const submit = async event => {
    event.preventDefault()
    if (submitting.current || !canEnter || !selectedReason || reasonLoading || !event.currentTarget.checkValidity()) return
    submitting.current = true; setSaving(true); setError(''); setMessage('')
    let result
    try {
      const payload = { employee_name: form.employee, leave_date: form.date, leave_reason: form.reason, detail: form.detail }
      if (selectedReason.requires_manual_penalty) payload.manual_penalty = Number(form.amount)
      result = await veraApi.createLeave(payload)
    } catch (error) { setError(error.message) }
    finally { submitting.current = false; setSaving(false) }
    if (result) {
      setOpen(false)
      setForm({ employee: '', date: today, reason: '', amount: '', detail: '' })
      setMessage(['Đã ghi phạt vi phạm.', ...(result.warnings || [])].join(' '))
      onSaved()
    }
  }

  return <section className="schedule-violations">
    <div className="schedule-violation-heading"><h3>VI PHẠM · PHẠT VI PHẠM</h3>{canEnter && <button type="button" className="primary-button" onClick={() => { setError(''); setOpen(true) }}>+ Nhập phạt vi phạm</button>}</div>
    <div className="schedule-violation-filters">
      <label>Tìm nhân viên<input type="search" placeholder="Tên hoặc tên đăng nhập…" value={search} onChange={event => setSearch(event.target.value)} /></label>
      <label>Ngày vi phạm<VeraDateInput value={filterDate} clearOnFocus={false} onChange={event => setFilterDate(event.target.value)} /></label>
      <div className="schedule-filter-bar" role="group" aria-label="Lọc thời gian vi phạm">{[['current', 'Tháng này'], ['previous', 'Tháng trước'], ['custom', 'Tuỳ chỉnh']].map(([value, label]) => <button type="button" key={value} className={period === value ? 'active' : ''} aria-pressed={period === value} onClick={() => { setPeriod(value); setFilterDate('') }}>{label}</button>)}</div>
      {period === 'custom' && <><label>Từ ngày<VeraDateInput value={customStart} clearOnFocus={false} onChange={event => setCustomStart(event.target.value)} /></label><label>Đến ngày<VeraDateInput value={customEnd} clearOnFocus={false} onChange={event => setCustomEnd(event.target.value)} /></label></>}
      <button type="button" className="secondary-button" onClick={() => { setSearch(''); setFilterDate('') }}>Bỏ lọc</button>
    </div>
    {message && <p role="status">{message}</p>}{state.error && <p role="alert">{state.error}</p>}
    <div className="schedule-scroll"><table><thead><tr><th>Nhân viên</th><th>Ngày vi phạm</th><th>Vi phạm</th>{canViewPenalty && <th>Phạt vi phạm</th>}<th>Ghi chú</th></tr></thead>
      <tbody>{rows.map(item => <tr key={item.record_uid}><td>{name(employeeMap.get(userKey(item.employee_name)))}</td><td>{formatVeraDate(item.leave_date)}</td><td>{item.leave_reason}</td>{canViewPenalty && <td className={Number(item.penalty) > 0 ? 'violation-positive' : ''}>{money(item.penalty)}</td>}<td>{item.detail || '—'}</td></tr>)}{!rows.length && <tr><td colSpan={canViewPenalty ? 5 : 4}>{state.loading ? 'Đang tải vi phạm…' : state.error ? 'Chưa tải được dữ liệu vi phạm.' : 'Không có vi phạm phù hợp bộ lọc.'}</td></tr>}</tbody>
      {canViewPenalty && rows.length > 0 && <tfoot><tr><td colSpan="3">Tổng</td><td>{money(rows.reduce((total, item) => total + Number(item.penalty || 0), 0))}</td><td /></tr></tfoot>}
    </table></div>
    {open && createPortal(<dialog ref={dialogRef} className="schedule-violation-dialog" aria-labelledby="schedule-violation-title" onCancel={event => { if (saving) event.preventDefault(); else setOpen(false) }}><form onSubmit={submit}>
      <div className="schedule-violation-heading"><h3 id="schedule-violation-title">NHẬP PHẠT VI PHẠM</h3><button type="button" className="secondary-button" disabled={saving} onClick={() => setOpen(false)}>Đóng</button></div>
      <div className="schedule-violation-form"><label>Nhân viên<select required value={form.employee} onChange={event => setForm({ ...form, employee: event.target.value })}><option value="">Chọn nhân viên</option>{employees.map(employee => <option key={employee.username} value={employee.username}>{name(employee)} · {employee.username}</option>)}</select></label>
        <label>Ngày vi phạm<VeraDateInput required value={form.date} clearOnFocus={false} onChange={event => setForm({ ...form, date: event.target.value, reason: '', amount: '' })} /></label>
        <label>Vi phạm<select required disabled={reasonLoading} value={form.reason} onChange={event => setForm({ ...form, reason: event.target.value, amount: '' })}><option value="">{reasonLoading ? 'Đang tải nội quy…' : 'Chọn vi phạm'}</option>{reasons.map(item => <option key={item.name} value={item.name}>{item.name}</option>)}</select></label>
        {selectedReason?.requires_manual_penalty ? <label>Số tiền phạt<VeraMoneyInput required value={form.amount} onChange={event => setForm({ ...form, amount: event.target.value })} /></label> : selectedReason && canViewPenalty && <label>Mức phạt theo nội quy<strong>{money(selectedReason.penalty)}</strong></label>}
        <label>Ghi chú<input value={form.detail} maxLength={500} onChange={event => setForm({ ...form, detail: event.target.value })} /></label>
      </div>{error && <p role="alert">{error}</p>}<button type="submit" className="primary-button" disabled={saving || reasonLoading || !selectedReason}>{saving ? 'Đang lưu…' : '+ Ghi phạt vi phạm'}</button>
    </form></dialog>, document.body)}
  </section>
}
