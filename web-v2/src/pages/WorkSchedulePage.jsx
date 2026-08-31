import { ClipboardPaste, Copy, LoaderCircle, Save } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'
import { getCurrentSession } from '../lib/supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const WEEKDAYS = ['CN', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']
const DEPARTMENTS = ['quanly', 'letan', 'locker']
const DEPARTMENT_PERMISSION = {
  quanly: 'work_schedule_quanly',
  letan: 'work_schedule_letan',
  locker: 'work_schedule_locker',
}
const SHIFT_INFO = {
  quanly: {
    label: 'Quản lý',
    mode: 'time',
  },
  locker: {
    label: 'Locker',
    mode: 'shift',
    shifts: { 'Ca 1': '09:30–17:30', 'Ca 2': '17:30–01:30 hôm sau' },
  },
  letan: {
    label: 'Lễ tân',
    mode: 'shift',
    shifts: { 'Ca 1': '09:00–17:00', 'Ca 2': '16:30–00:30 hôm sau' },
  },
}

function isoDate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function displayDate(date) {
  return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')}`
}

function currentAndNextWeekDays() {
  const today = new Date()
  const currentDay = today.getDay()
  const offsetToMonday = currentDay === 0 ? -6 : 1 - currentDay
  const monday = new Date(today)
  monday.setHours(12, 0, 0, 0)
  monday.setDate(today.getDate() + offsetToMonday)
  return Array.from({ length: 14 }, (_, index) => {
    const item = new Date(monday)
    item.setDate(monday.getDate() + index)
    return item
  })
}

function keyFor(username, day) { return `${username}__${day}` }

function emptyCell() {
  return { shift_code: '', overtime_shift: '', start_time: '', end_time: '', note: '' }
}

async function scheduleRequest(path, options = {}) {
  if (!API_BASE) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload?.detail || payload?.message || 'Không thực hiện được thao tác lịch làm việc.')
  return payload
}

export default function WorkSchedulePage({ user }) {
  const days = useMemo(() => currentAndNextWeekDays(), [])
  const todayIso = isoDate(new Date())
  const availableDepartments = useMemo(() => {
    if (String(user?.role || '').toLowerCase() === 'admin') return DEPARTMENTS
    return DEPARTMENTS.filter((item) => user?.permissions?.[DEPARTMENT_PERMISSION[item]] === true)
  }, [user?.permissions, user?.role])

  const [department, setDepartment] = useState(availableDepartments[0] || 'quanly')
  const [employees, setEmployees] = useState([])
  const [saved, setSaved] = useState({})
  const [drafts, setDrafts] = useState({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [selectedCell, setSelectedCell] = useState(null)
  const [clipboardCell, setClipboardCell] = useState(null)
  const roleCanEdit = ['admin', 'quanly'].includes(String(user?.role || '').toLowerCase())
  const canEdit = roleCanEdit && availableDepartments.includes(department)
  const rangeLabel = `${displayDate(days[0])}/${days[0].getFullYear()} – ${displayDate(days[13])}/${days[13].getFullYear()}`

  useEffect(() => {
    if (!availableDepartments.length) return
    if (!availableDepartments.includes(department)) setDepartment(availableDepartments[0])
  }, [availableDepartments, department])

  const load = async () => {
    if (!availableDepartments.length || !availableDepartments.includes(department)) {
      setEmployees([])
      setSaved({})
      setDrafts({})
      setLoading(false)
      return
    }
    setLoading(true)
    setNotice('')
    setSelectedCell(null)
    try {
      const staff = await veraApi.staff()
      const wanted = (staff.employees || []).filter((item) => (
        String(item.role || '').toLowerCase() === department
        && item.employment_status !== 'Đã nghỉ việc'
      ))
      setEmployees(wanted)
      const start = isoDate(days[0])
      const end = isoDate(days[days.length - 1])
      const result = await scheduleRequest(`/v2/work-schedule?start=${start}&end=${end}&department=${department}`)
      const mapped = Object.fromEntries((result.rows || []).map((row) => [keyFor(row.employee_username, row.work_date), {
        shift_code: row.shift_code || '',
        overtime_shift: row.overtime_shift || '',
        start_time: String(row.start_time || '').slice(0, 5),
        end_time: String(row.end_time || '').slice(0, 5),
        note: row.note || '',
      }]))
      setSaved(mapped)
      setDrafts(mapped)
    } catch (error) {
      setNotice(error.message || 'Không tải được lịch làm việc.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [department]) // eslint-disable-line react-hooks/exhaustive-deps

  const setCell = (username, day, field, value) => {
    const key = keyFor(username, day)
    setDrafts((current) => {
      const next = { ...emptyCell(), ...(current[key] || {}), [field]: value }
      if (field === 'shift_code' && value === '') return { ...current, [key]: emptyCell() }
      if (field === 'shift_code' && value === 'Nghỉ') {
        next.overtime_shift = ''
        next.start_time = ''
        next.end_time = ''
      }
      if (department === 'quanly') next.overtime_shift = ''
      return { ...current, [key]: next }
    })
  }

  const copyCell = async (username, day) => {
    const key = keyFor(username, day)
    const payload = { department, value: { ...emptyCell(), ...(drafts[key] || {}) } }
    setClipboardCell(payload)
    setSelectedCell({ username, day })
    try {
      await navigator.clipboard?.writeText(`VERA_SCHEDULE:${JSON.stringify(payload)}`)
    } catch {
      // Internal clipboard remains available even when browser clipboard is blocked.
    }
    setNotice(`Đã sao chép ô ${day}. Chọn ô khác và Dán hoặc nhấn Ctrl+V.`)
  }

  const pasteCell = async (username, day) => {
    if (!canEdit) return
    let payload = clipboardCell
    try {
      const raw = await navigator.clipboard?.readText()
      if (raw?.startsWith('VERA_SCHEDULE:')) payload = JSON.parse(raw.slice('VERA_SCHEDULE:'.length))
    } catch {
      // Fall back to internal clipboard.
    }
    if (!payload?.value) {
      setNotice('Chưa có ô lịch nào được sao chép.')
      return
    }
    if (payload.department !== department) {
      setNotice(`Không thể dán dữ liệu ${SHIFT_INFO[payload.department]?.label || payload.department} sang ${SHIFT_INFO[department].label}.`)
      return
    }
    const key = keyFor(username, day)
    setDrafts((current) => ({ ...current, [key]: { ...emptyCell(), ...payload.value } }))
    setSelectedCell({ username, day })
    setNotice(`Đã dán vào ngày ${day}. Bấm Lưu lịch để ghi chính thức.`)
  }

  const selectedCopy = () => {
    if (!selectedCell) return
    void copyCell(selectedCell.username, selectedCell.day)
  }

  const selectedPaste = () => {
    if (!selectedCell) return
    void pasteCell(selectedCell.username, selectedCell.day)
  }

  const handleCellKeyDown = (event, username, day) => {
    if (!(event.ctrlKey || event.metaKey)) return
    if (event.key.toLowerCase() === 'c') {
      event.preventDefault()
      void copyCell(username, day)
    }
    if (event.key.toLowerCase() === 'v') {
      event.preventDefault()
      void pasteCell(username, day)
    }
  }

  const saveChanges = async () => {
    if (!canEdit) return
    setBusy(true)
    setNotice('')
    try {
      const rows = []
      const deletes = []
      for (const employee of employees) {
        for (const date of days) {
          const day = isoDate(date)
          const key = keyFor(employee.username, day)
          const before = { ...emptyCell(), ...(saved[key] || {}) }
          const after = { ...emptyCell(), ...(drafts[key] || {}) }
          if (JSON.stringify(before) === JSON.stringify(after)) continue
          if (!after.shift_code) {
            if (before.shift_code) deletes.push({ day, username: employee.username })
            continue
          }
          if (department === 'quanly' && after.shift_code === 'Giờ làm' && (!after.start_time || !after.end_time)) {
            throw new Error(`${employee.full_name || employee.username} · ${day}: cần đủ giờ bắt đầu và giờ kết thúc.`)
          }
          rows.push({
            work_date: day,
            employee_username: employee.username,
            employee_name: employee.full_name || employee.username,
            department,
            shift_code: after.shift_code,
            overtime_shift: department === 'quanly' ? '' : (after.overtime_shift || ''),
            start_time: department === 'quanly' ? (after.start_time || '') : '',
            end_time: department === 'quanly' ? (after.end_time || '') : '',
            note: after.note || '',
          })
        }
      }
      if (!rows.length && !deletes.length) throw new Error('Chưa có thay đổi cần lưu.')
      if (rows.length) await scheduleRequest('/v2/work-schedule', { method: 'PUT', body: JSON.stringify({ rows }) })
      for (const item of deletes) {
        await scheduleRequest(`/v2/work-schedule?work_date=${item.day}&employee_username=${encodeURIComponent(item.username)}`, { method: 'DELETE' })
      }
      await load()
      setNotice(`Đã lưu ${rows.length + deletes.length} thay đổi lịch làm việc.`)
    } catch (error) {
      setNotice(error.message || 'Không lưu được lịch làm việc.')
    } finally {
      setBusy(false)
    }
  }

  if (!availableDepartments.length) {
    return <section className="work-schedule-page"><div className="warning-box">Tài khoản chưa được cấp quyền Lịch làm việc Quản lý, Lễ tân hoặc Locker.</div></section>
  }

  return (
    <section className="work-schedule-page">
      <style>{`
        .work-schedule-page{display:grid;gap:16px}.schedule-head{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}.schedule-title h2{margin:0}.schedule-title p{margin:4px 0 0;color:#64748b}.schedule-range{margin-top:7px;font-size:13px;font-weight:800;color:#1f513f}.schedule-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.schedule-tools select,.shift-select,.ot-select,.manager-status,.manager-time{border:1px solid #d9e2df;border-radius:9px;padding:8px;background:#fff}.schedule-legend{display:flex;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid #dfe8e5;border-radius:12px;background:#f8fbfa;font-size:13px}.schedule-scroll{overflow:auto;border:1px solid #dfe8e5;border-radius:14px;background:#fff}.schedule-grid{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}.schedule-grid th,.schedule-grid td{border-right:1px solid #e6ecea;border-bottom:1px solid #e6ecea;padding:6px;text-align:center;vertical-align:middle}.schedule-grid thead th{position:sticky;top:0;background:#eef6f3;z-index:3;min-width:116px}.schedule-grid thead tr:nth-child(2) th{top:35px}.schedule-grid thead th.employee-head{left:0;z-index:6;min-width:190px}.schedule-grid td.employee-cell{position:sticky;left:0;background:#fff;z-index:2;text-align:left;min-width:190px}.schedule-grid .week-head{height:35px;background:#dfeee8;font-weight:900;color:#244a3a}.schedule-grid .sunday{background:#fff6f2}.schedule-grid .today{box-shadow:inset 0 0 0 2px #bb8b34}.schedule-grid td.selected{box-shadow:inset 0 0 0 3px #245b47;background:#eff8f4}.schedule-cell{display:grid;gap:5px}.shift-select,.ot-select{width:104px;padding:5px;font-size:12px}.shift-select.ca1{background:#dff3cc}.shift-select.ca2{background:#fff8a8}.shift-select.off,.manager-status.off{background:#ffe0b8}.ot-select.active{font-weight:700}.manager-cell{display:grid;gap:5px;min-width:136px}.manager-status{width:126px;padding:5px;font-size:12px}.manager-time-row{display:grid;grid-template-columns:1fr 1fr;gap:4px}.manager-time{width:61px;min-width:0;padding:5px 3px;font-size:11px}.schedule-save,.schedule-copy-button{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:9px 13px;font-weight:700}.schedule-save{background:#173329;color:white}.schedule-copy-button{background:#eef5f2;color:#214538;border:1px solid #ccddd5}.schedule-save:disabled,.schedule-copy-button:disabled{opacity:.5}.schedule-notice{padding:10px 12px;border-radius:10px;background:#edf7f3}.employee-role{display:block;color:#708079;font-size:12px;margin-top:2px}.schedule-help{font-size:12px;color:#66766f}.schedule-department-tabs{display:flex;gap:6px;flex-wrap:wrap}.schedule-department-tabs button{border:1px solid #d7e2dd;background:#fff;border-radius:10px;padding:8px 11px;font-weight:800;color:#4a5d55}.schedule-department-tabs button.active{background:#173329;color:#fff;border-color:#173329}@media(max-width:700px){.schedule-title p{font-size:13px}.schedule-grid thead th.employee-head,.schedule-grid td.employee-cell{min-width:145px}.schedule-grid thead th{min-width:108px}.schedule-tools{width:100%}.schedule-copy-button,.schedule-save{flex:1;justify-content:center}}
      `}</style>
      <div className="schedule-head">
        <div className="schedule-title">
          <h2>Lịch làm việc</h2>
          <p>Sắp lịch từng ngày, không dùng chu kỳ. Màn hình luôn hiển thị Tuần này + Tuần sau, đủ 14 ngày.</p>
          <div className="schedule-range">{rangeLabel}</div>
        </div>
        <div className="schedule-tools">
          <button type="button" className="schedule-copy-button" onClick={selectedCopy} disabled={!selectedCell}><Copy size={16}/> Sao chép ô</button>
          <button type="button" className="schedule-copy-button" onClick={selectedPaste} disabled={!selectedCell || !canEdit}><ClipboardPaste size={16}/> Dán ô</button>
          {canEdit && <button type="button" className="schedule-save" onClick={saveChanges} disabled={busy || loading}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />} Lưu lịch</button>}
        </div>
      </div>

      <div className="schedule-department-tabs">
        {availableDepartments.map((item) => <button type="button" key={item} className={department === item ? 'active' : ''} onClick={() => setDepartment(item)}>{SHIFT_INFO[item].label}</button>)}
      </div>

      {department === 'quanly'
        ? <div className="schedule-legend"><strong>Quản lý</strong><span>Mỗi ngày nhập riêng Giờ bắt đầu → Giờ kết thúc.</span><span>Không áp dụng Ca 1/Ca 2.</span></div>
        : <div className="schedule-legend"><strong>{SHIFT_INFO[department].label}</strong><span>Ca 1: {SHIFT_INFO[department].shifts['Ca 1']}</span><span>Ca 2: {SHIFT_INFO[department].shifts['Ca 2']}</span><span>Tăng ca: TC Ca 1 / TC Ca 2</span></div>}
      <div className="schedule-help">Chọn một ô để Sao chép/Dán. Trên máy tính có thể dùng trực tiếp Ctrl+C và Ctrl+V giữa các ô cùng bộ phận.</div>
      {notice && <div className="schedule-notice">{notice}</div>}

      {loading ? <div className="page-loading"><LoaderCircle size={18} className="spin" /> Đang tải lịch…</div> : (
        <div className="schedule-scroll">
          <table className="schedule-grid">
            <thead>
              <tr><th className="employee-head" rowSpan="2">Tên nhân viên</th><th className="week-head" colSpan="7">TUẦN NÀY</th><th className="week-head" colSpan="7">TUẦN SAU</th></tr>
              <tr>{days.map((date) => {
                const day = isoDate(date)
                const classes = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : ''].filter(Boolean).join(' ')
                return <th key={day} className={classes}><div>{WEEKDAYS[date.getDay()]}</div><small>{displayDate(date)}</small></th>
              })}</tr>
            </thead>
            <tbody>{employees.map((employee) => <tr key={employee.username}>
              <td className="employee-cell"><strong>{employee.full_name || employee.username}</strong><span className="employee-role">{SHIFT_INFO[department].label}</span></td>
              {days.map((date) => {
                const day = isoDate(date)
                const cellKey = keyFor(employee.username, day)
                const value = { ...emptyCell(), ...(drafts[cellKey] || {}) }
                const isSelected = selectedCell?.username === employee.username && selectedCell?.day === day
                const tdClass = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : '', isSelected ? 'selected' : ''].filter(Boolean).join(' ')
                const shiftClass = value.shift_code === 'Ca 1' ? 'ca1' : value.shift_code === 'Ca 2' ? 'ca2' : value.shift_code === 'Nghỉ' ? 'off' : ''
                return <td key={day} className={tdClass} tabIndex={0} onFocus={() => setSelectedCell({ username: employee.username, day })} onClick={() => setSelectedCell({ username: employee.username, day })} onKeyDown={(event) => handleCellKeyDown(event, employee.username, day)}>
                  {department === 'quanly' ? <div className="manager-cell">
                    <select className={`manager-status ${value.shift_code === 'Nghỉ' ? 'off' : ''}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
                      <option value="">—</option><option value="Giờ làm">Làm việc</option><option value="Nghỉ">Nghỉ</option>
                    </select>
                    {value.shift_code === 'Giờ làm' && <div className="manager-time-row"><input className="manager-time" type="time" value={value.start_time || ''} disabled={!canEdit} aria-label={`Giờ bắt đầu ${day}`} onChange={(event) => setCell(employee.username, day, 'start_time', event.target.value)} /><input className="manager-time" type="time" value={value.end_time || ''} disabled={!canEdit} aria-label={`Giờ kết thúc ${day}`} onChange={(event) => setCell(employee.username, day, 'end_time', event.target.value)} /></div>}
                  </div> : <div className="schedule-cell">
                    <select className={`shift-select ${shiftClass}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}><option value="">—</option><option>Ca 1</option><option>Ca 2</option><option>Nghỉ</option></select>
                    <select className={`ot-select ${value.overtime_shift ? 'active' : ''}`} value={value.overtime_shift || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(event) => setCell(employee.username, day, 'overtime_shift', event.target.value)}><option value="">Không TC</option><option>TC Ca 1</option><option>TC Ca 2</option></select>
                  </div>}
                </td>
              })}
            </tr>)}</tbody>
          </table>
          {!employees.length && <div className="revenue-meta">Không có nhân viên đang hiển thị trong nhóm {SHIFT_INFO[department].label}.</div>}
        </div>
      )}
    </section>
  )
}
