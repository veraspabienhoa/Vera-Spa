import { violationMonthRange } from '../lib/businessMonthRange'
import { useCallback, useEffect, useRef, useState } from 'react'
import VeraDateInput from './VeraDateInput'
import VeraMoneyInput from './VeraMoneyInput'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import { searchTextMatches } from '../lib/searchText'

const money = value => `${Number(value || 0).toLocaleString('vi-VN')}đ`

export default function ScheduleViolations({ department, departmentLabel, employees = [], canEdit, canManage = false, personal = false, openSequence, request, onSaved, onExport }) {
  const [mode, setMode] = useState('month')
  const [range, setRange] = useState(() => violationMonthRange())
  const [search, setSearch] = useState('')
  const [date, setDate] = useState('')
  const [rows, setRows] = useState([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState('')
  const [notice, setNotice] = useState('')
  const [revision, setRevision] = useState(0)
  const [busy, setBusy] = useState(false)
  const [exporting, setExporting] = useState(false)
  const [form, setForm] = useState(null)
  const dialog = useRef(null)
  const submitting = useRef(false)
  const requestRef = useRef(request)
  requestRef.current = request
  useEffect(() => {
    let active = true
    setRows([])
    if (!range.start || !range.end || range.end < range.start) { setError('Vui lòng nhập khoảng ngày hợp lệ.'); setLoading(false); return }
    setLoading(true); setError('')
    const path = personal ? '/v2/work-schedule/violations/me?' : `/v2/work-schedule/violations?department=${encodeURIComponent(department)}&`
    requestRef.current(`${path}start=${range.start}&end=${range.end}`)
      .then(result => { if (active) setRows(result.rows || []) })
      .catch(err => { if (active) setError(err.message) })
      .finally(() => { if (active) setLoading(false) })
    return () => { active = false }
  }, [department, personal, range.start, range.end, revision])
  useEffect(() => { dialog.current?.close(); setForm(null); setNotice('') }, [department])
  const selectRange = value => {
    setMode(value); setDate('')
    if (value !== 'custom') setRange(violationMonthRange(value === 'last_month' ? -1 : 0))
  }
  const open = useCallback(() => {
    setNotice('')
    setForm({ request_id: crypto.randomUUID(), employee_username: '', violation_date: violationMonthRange().today, reason: '', amount: '', note: '' })
    dialog.current.showModal()
  }, [])
  useEffect(() => { if (openSequence > 0 && canEdit) open() }, [openSequence, canEdit, open])
  const save = async event => {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true; setBusy(true); setNotice('')
    try {
      const result = await requestRef.current(form.id ? `/v2/work-schedule/violations/${encodeURIComponent(form.id)}` : '/v2/work-schedule/violations', { method: form.id ? 'PUT' : 'POST', body: JSON.stringify({ ...form, amount: Number(form.amount || 0), department }) })
      setNotice(result.message); dialog.current.close(); setForm(null)
      setRevision(value => value + 1); onSaved()
    } catch (err) { setNotice(err.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  const edit = row => {
    setNotice('')
    setForm({ ...row, expected_updated_at: row.updated_at })
    dialog.current.showModal()
  }
  const remove = async row => {
    if (submitting.current || !window.confirm(`Xóa vi phạm của ${row.employee_name} ngày ${formatVeraDate(row.violation_date)}?`)) return
    submitting.current = true; setBusy(true); setNotice('')
    try {
      const result = await requestRef.current(`/v2/work-schedule/violations/${encodeURIComponent(row.id)}`, { method: 'DELETE', body: JSON.stringify({ department, expected_updated_at: row.updated_at }) })
      setNotice(result.message); setRevision(value => value + 1); onSaved()
    } catch (err) { setNotice(err.message) }
    finally { submitting.current = false; setBusy(false) }
  }
  const visible = rows.filter(row => (!date || row.violation_date === date) && searchTextMatches(`${row.employee_name} ${row.employee_username}`, search))
  const exportVisible = async () => {
    setExporting(true); setNotice('')
    try { await onExport({ range: date ? { start: date, end: date } : range, rows: visible }) }
    catch (err) { setNotice(err.message || 'Không xuất được bảng vi phạm.') }
    finally { setExporting(false) }
  }
  return <section className="panel schedule-violations">
    <div className="schedule-violation-title"><h3>{personal ? 'LỊCH SỬ VI PHẠM CỦA TÔI' : `VI PHẠM · PHẠT VI PHẠM${departmentLabel ? ` · ${departmentLabel}` : ''}`}</h3>{onExport && <button className="secondary-button" type="button" disabled={loading || exporting || Boolean(error) || busy} onClick={() => void exportVisible()}>{exporting ? 'Đang xuất…' : 'Xuất excel'}</button>}{canEdit && openSequence === undefined && <button className="primary-button" type="button" onClick={open}>+ Nhập phạt vi phạm</button>}</div>
    <div className="schedule-violation-filters">
      {!personal && <label>Tên nhân viên<input type="search" placeholder="Tìm tên nhân viên…" value={search} onChange={e => setSearch(e.target.value)} /></label>}
      <label>Ngày vi phạm<VeraDateInput value={date} aria-label="Lọc ngày vi phạm" onChange={e => setDate(e.target.value)} /></label>
      {[['month', 'Tháng này'], ['last_month', 'Tháng trước'], ['custom', 'Tùy chỉnh']].map(([value, label]) => <button key={value} type="button" className={mode === value ? 'primary-button' : 'secondary-button'} aria-pressed={mode === value} onClick={() => selectRange(value)}>{label}</button>)}
      {mode === 'custom' && <><label>Từ ngày<VeraDateInput value={range.start} onChange={e => setRange({ ...range, start: e.target.value })} /></label><label>Đến ngày<VeraDateInput value={range.end} onChange={e => setRange({ ...range, end: e.target.value })} /></label></>}
    </div>
    {notice && <p role="status">{notice}</p>}{error && <div className="error-box" role="alert">{error}</div>}
    <p>{visible.length} vi phạm · Tổng tiền phạt: <strong>{money(visible.reduce((sum, row) => sum + Number(row.amount), 0))}</strong></p>
    <div className="schedule-scroll"><table><thead><tr><th>Nhân viên</th><th>Ngày vi phạm</th><th>Nội dung vi phạm</th><th>Tiền phạt</th><th>Ghi chú</th><th>Người nhập</th><th>Ngày ghi nhận</th>{canManage && <th>Thao tác</th>}</tr></thead><tbody>
      {visible.map((row, index) => <tr key={row.id || index}><td>{row.employee_name}<small>{row.employee_username}</small></td><td>{formatVeraDate(row.violation_date)}</td><td>{row.reason}</td><td>{money(row.amount)}</td><td>{row.note}</td><td>{row.updated_by}</td><td>{formatVeraDateTime(row.created_at)}</td>{canManage && <td><div className="schedule-violation-row-actions"><button type="button" className="secondary-button" disabled={busy || !row.id || !row.updated_at} onClick={() => edit(row)}>Sửa</button><button type="button" className="danger-button" disabled={busy || !row.id || !row.updated_at} onClick={() => void remove(row)}>Xóa</button></div></td>}</tr>)}
      {!visible.length && <tr><td colSpan={canManage ? 8 : 7}>{loading ? 'Đang tải…' : 'Không có vi phạm theo bộ lọc.'}</td></tr>}
    </tbody></table></div>
    <dialog ref={dialog} className="schedule-violation-dialog" onCancel={e => { if (busy) e.preventDefault() }}>
      {form && <form onSubmit={save}><h3>{form.id ? 'SỬA VI PHẠM · PHẠT VI PHẠM' : 'NHẬP PHẠT VI PHẠM'}</h3><div className="schedule-violation-form">
        <label>Nhân viên<select required disabled={Boolean(form.id)} value={form.employee_username} onChange={e => setForm({ ...form, employee_username: e.target.value })}><option value="">Chọn nhân viên</option>{employees.map(employee => <option key={employee.username} value={employee.username}>{employee.full_name || employee.username} · {employee.username}</option>)}</select></label>
        <label>Ngày vi phạm<VeraDateInput required disabled={Boolean(form.id && !form.is_manual)} clearOnFocus={false} value={form.violation_date} onChange={e => setForm({ ...form, violation_date: e.target.value })} /></label>
        <label>Nội dung vi phạm<input required disabled={Boolean(form.id && !form.is_manual)} maxLength={400} value={form.reason} onChange={e => setForm({ ...form, reason: e.target.value })} /></label>
        <label>Tiền phạt<VeraMoneyInput value={form.amount} onChange={e => setForm({ ...form, amount: e.target.value })} /></label>
        <label>Ghi chú<input maxLength={1000} value={form.note} onChange={e => setForm({ ...form, note: e.target.value })} /></label>
      </div>{notice && <p role="alert">{notice}</p>}<div className="schedule-violation-title"><button type="button" className="secondary-button" disabled={busy} onClick={() => { dialog.current.close(); setForm(null) }}>Đóng</button><button type="submit" className="primary-button" disabled={busy}>{busy ? 'Đang lưu…' : form.id ? 'Lưu sửa' : 'Lưu phạt vi phạm'}</button></div></form>}
    </dialog>
  </section>
}
