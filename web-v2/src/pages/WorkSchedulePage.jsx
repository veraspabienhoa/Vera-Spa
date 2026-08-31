import { ChevronLeft, ChevronRight, LoaderCircle, Save } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'
import { getCurrentSession } from '../lib/supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const WEEKDAYS = ['CN', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']
const SHIFT_INFO = {
  locker: {
    label: 'Locker',
    shifts: { 'Ca 1': '09:30–17:30', 'Ca 2': '17:30–01:30 hôm sau' },
  },
  letan: {
    label: 'Lễ tân',
    shifts: { 'Ca 1': '09:00–17:00', 'Ca 2': '16:30–00:30 hôm sau' },
  },
}

function isoDate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function monthDays(monthValue) {
  const [year, month] = monthValue.split('-').map(Number)
  const last = new Date(year, month, 0).getDate()
  return Array.from({ length: last }, (_, index) => new Date(year, month - 1, index + 1))
}

function keyFor(username, day) { return `${username}__${day}` }

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
  const now = new Date()
  const [month, setMonth] = useState(`${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`)
  const [department, setDepartment] = useState('locker')
  const [employees, setEmployees] = useState([])
  const [saved, setSaved] = useState({})
  const [drafts, setDrafts] = useState({})
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const days = useMemo(() => monthDays(month), [month])
  const canEdit = ['admin', 'quanly'].includes(String(user?.role || '').toLowerCase())

  const load = async () => {
    setLoading(true); setNotice('')
    try {
      const staff = await veraApi.staff()
      const wanted = (staff.employees || []).filter((item) => item.role === department && item.employment_status !== 'Đã nghỉ việc')
      setEmployees(wanted)
      const start = isoDate(days[0]); const end = isoDate(days[days.length - 1])
      const result = await scheduleRequest(`/v2/work-schedule?start=${start}&end=${end}&department=${department}`)
      const mapped = Object.fromEntries((result.rows || []).map((row) => [keyFor(row.employee_username, row.work_date), {
        shift_code: row.shift_code || '', overtime_shift: row.overtime_shift || '', note: row.note || '',
      }]))
      setSaved(mapped); setDrafts(mapped)
    } catch (error) {
      setNotice(error.message || 'Không tải được lịch làm việc.')
    } finally { setLoading(false) }
  }

  useEffect(() => { load() }, [month, department])

  const setCell = (username, day, field, value) => {
    const key = keyFor(username, day)
    setDrafts((current) => ({ ...current, [key]: { shift_code: '', overtime_shift: '', note: '', ...(current[key] || {}), [field]: value } }))
  }

  const moveMonth = (delta) => {
    const [year, monthNo] = month.split('-').map(Number)
    const next = new Date(year, monthNo - 1 + delta, 1)
    setMonth(`${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`)
  }

  const saveChanges = async () => {
    if (!canEdit) return
    setBusy(true); setNotice('')
    try {
      const rows = []
      const deletes = []
      for (const employee of employees) {
        for (const date of days) {
          const day = isoDate(date); const key = keyFor(employee.username, day)
          const before = saved[key] || { shift_code: '', overtime_shift: '', note: '' }
          const after = drafts[key] || { shift_code: '', overtime_shift: '', note: '' }
          if (JSON.stringify(before) === JSON.stringify(after)) continue
          if (!after.shift_code) {
            if (before.shift_code) deletes.push({ day, username: employee.username })
            continue
          }
          rows.push({
            work_date: day,
            employee_username: employee.username,
            employee_name: employee.full_name || employee.username,
            department,
            shift_code: after.shift_code,
            overtime_shift: after.overtime_shift || '',
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
    } finally { setBusy(false) }
  }

  return (
    <section className="work-schedule-page">
      <style>{`
        .work-schedule-page{display:grid;gap:16px}.schedule-head{display:flex;gap:12px;align-items:center;justify-content:space-between;flex-wrap:wrap}.schedule-title h2{margin:0}.schedule-title p{margin:4px 0 0;color:#64748b}.schedule-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.schedule-tools select,.schedule-tools input,.shift-select,.ot-select{border:1px solid #d9e2df;border-radius:9px;padding:8px;background:#fff}.schedule-legend{display:flex;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid #dfe8e5;border-radius:12px;background:#f8fbfa;font-size:13px}.schedule-scroll{overflow:auto;border:1px solid #dfe8e5;border-radius:14px;background:#fff}.schedule-grid{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}.schedule-grid th,.schedule-grid td{border-right:1px solid #e6ecea;border-bottom:1px solid #e6ecea;padding:6px;text-align:center;vertical-align:middle}.schedule-grid thead th{position:sticky;top:0;background:#eef6f3;z-index:3;min-width:116px}.schedule-grid thead th.employee-head{left:0;z-index:5;min-width:190px}.schedule-grid td.employee-cell{position:sticky;left:0;background:#fff;z-index:2;text-align:left;min-width:190px}.schedule-grid .sunday{background:#fff6f2}.schedule-cell{display:grid;gap:5px}.shift-select,.ot-select{width:104px;padding:5px;font-size:12px}.shift-select.ca1{background:#dff3cc}.shift-select.ca2{background:#fff8a8}.shift-select.off{background:#ffe0b8}.ot-select.active{font-weight:700}.schedule-save{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:9px 13px;background:#173329;color:white;font-weight:700}.schedule-save:disabled{opacity:.55}.schedule-notice{padding:10px 12px;border-radius:10px;background:#edf7f3}.schedule-month-nav{display:flex;gap:4px;align-items:center}.schedule-month-nav button{border:1px solid #d9e2df;background:#fff;border-radius:9px;padding:7px}.employee-role{display:block;color:#708079;font-size:12px;margin-top:2px}@media(max-width:700px){.schedule-title p{font-size:13px}.schedule-grid thead th.employee-head,.schedule-grid td.employee-cell{min-width:145px}.schedule-grid thead th{min-width:108px}}
      `}</style>
      <div className="schedule-head">
        <div className="schedule-title"><h2>Lịch làm việc</h2><p>Sắp ca theo từng ngày thực tế, không áp dụng chu kỳ xoay ca.</p></div>
        <div className="schedule-tools">
          <select value={department} onChange={(e) => setDepartment(e.target.value)}><option value="locker">Locker</option><option value="letan">Lễ tân</option></select>
          <div className="schedule-month-nav"><button type="button" onClick={() => moveMonth(-1)}><ChevronLeft size={17} /></button><input type="month" value={month} onChange={(e) => setMonth(e.target.value)} /><button type="button" onClick={() => moveMonth(1)}><ChevronRight size={17} /></button></div>
          {canEdit && <button type="button" className="schedule-save" onClick={saveChanges} disabled={busy || loading}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />} Lưu lịch</button>}
        </div>
      </div>

      <div className="schedule-legend"><strong>{SHIFT_INFO[department].label}</strong><span>Ca 1: {SHIFT_INFO[department].shifts['Ca 1']}</span><span>Ca 2: {SHIFT_INFO[department].shifts['Ca 2']}</span><span>Tăng ca: chọn riêng TC Ca 1 / TC Ca 2</span></div>
      {notice && <div className="schedule-notice">{notice}</div>}
      {loading ? <div className="page-loading"><LoaderCircle size={18} className="spin" /> Đang tải lịch…</div> : (
        <div className="schedule-scroll">
          <table className="schedule-grid">
            <thead><tr><th className="employee-head">Tên nhân viên</th>{days.map((date) => <th key={isoDate(date)} className={date.getDay() === 0 ? 'sunday' : ''}><div>{WEEKDAYS[date.getDay()]}</div><small>{date.getDate()}/{date.getMonth() + 1}</small></th>)}</tr></thead>
            <tbody>{employees.map((employee) => <tr key={employee.username}>
              <td className="employee-cell"><strong>{employee.full_name || employee.username}</strong><span className="employee-role">{SHIFT_INFO[department].label}</span></td>
              {days.map((date) => {
                const day = isoDate(date); const value = drafts[keyFor(employee.username, day)] || { shift_code: '', overtime_shift: '' }
                const shiftClass = value.shift_code === 'Ca 1' ? 'ca1' : value.shift_code === 'Ca 2' ? 'ca2' : value.shift_code === 'Nghỉ' ? 'off' : ''
                return <td key={day} className={date.getDay() === 0 ? 'sunday' : ''}><div className="schedule-cell">
                  <select className={`shift-select ${shiftClass}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(e) => setCell(employee.username, day, 'shift_code', e.target.value)}><option value="">—</option><option>Ca 1</option><option>Ca 2</option><option>Nghỉ</option></select>
                  <select className={`ot-select ${value.overtime_shift ? 'active' : ''}`} value={value.overtime_shift || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(e) => setCell(employee.username, day, 'overtime_shift', e.target.value)}><option value="">Không TC</option><option>TC Ca 1</option><option>TC Ca 2</option></select>
                </div></td>
              })}
            </tr>)}</tbody>
          </table>
        </div>
      )}
    </section>
  )
}
