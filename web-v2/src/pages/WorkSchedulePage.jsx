import {
  CalendarDays, ChevronLeft, ChevronRight, ClipboardPaste, Copy, LoaderCircle,
  Plus, Save, Settings2, Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const WEEKDAYS = ['CN', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']
const DEPARTMENTS = ['quanly', 'letan', 'locker']
const DEPARTMENT_PERMISSION = {
  quanly: 'work_schedule_quanly',
  letan: 'work_schedule_letan',
  locker: 'work_schedule_locker',
}
const DEPARTMENT_INFO = {
  quanly: { label: 'Quản lý', mode: 'time' },
  letan: { label: 'Lễ tân', mode: 'shift' },
  locker: { label: 'Locker', mode: 'shift' },
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

function currentMonthValue() {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

function monthDays(monthValue) {
  const match = String(monthValue || '').match(/^(\d{4})-(\d{2})$/)
  const now = new Date()
  const year = match ? Number(match[1]) : now.getFullYear()
  const month = match ? Number(match[2]) - 1 : now.getMonth()
  const count = new Date(year, month + 1, 0).getDate()
  return Array.from({ length: count }, (_, index) => new Date(year, month, index + 1, 12, 0, 0, 0))
}

function moveMonth(monthValue, amount) {
  const [year, month] = monthValue.split('-').map(Number)
  const next = new Date(year, month - 1 + amount, 1, 12, 0, 0, 0)
  return `${next.getFullYear()}-${String(next.getMonth() + 1).padStart(2, '0')}`
}

function preferredDepartment(user, available) {
  const role = String(user?.role || '').toLowerCase()
  return available.includes(role) ? role : (available[0] || 'quanly')
}

function keyFor(username, day) { return `${username}__${day}` }

function emptyCell() {
  return {
    shift_code: '', overtime_shift: '', start_time: '', end_time: '',
    overtime_start_time: '', overtime_end_time: '', note: '',
  }
}

function formatShiftTime(spec) {
  if (!spec?.start || !spec?.end) return 'Chưa cài giờ'
  return `${spec.start}–${spec.end}${spec.end_next_day ? ' hôm sau' : ''}`
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
  const todayIso = isoDate(new Date())
  const [month, setMonth] = useState(currentMonthValue())
  const days = useMemo(() => monthDays(month), [month])
  const availableDepartments = useMemo(() => {
    if (String(user?.role || '').toLowerCase() === 'admin') return DEPARTMENTS
    return DEPARTMENTS.filter((item) => user?.permissions?.[DEPARTMENT_PERMISSION[item]] === true)
  }, [user?.permissions, user?.role])

  const [department, setDepartment] = useState(() => preferredDepartment(user, availableDepartments))
  const [employees, setEmployees] = useState([])
  const [saved, setSaved] = useState({})
  const [drafts, setDrafts] = useState({})
  const [shiftDefinitions, setShiftDefinitions] = useState({ quanly: {}, letan: {}, locker: {} })
  const [shiftDrafts, setShiftDrafts] = useState([])
  const [shiftEditorOpen, setShiftEditorOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [selectedCell, setSelectedCell] = useState(null)
  const [clipboardCell, setClipboardCell] = useState(null)
  const [pastePanelOpen, setPastePanelOpen] = useState(false)
  const [pasteEndDay, setPasteEndDay] = useState('')

  const roleCanEdit = ['admin', 'quanly'].includes(String(user?.role || '').toLowerCase())
  const canEdit = roleCanEdit && availableDepartments.includes(department)
  const ownUsername = String(user?.employee_username || '').trim().toLowerCase()
  const rangeLabel = `${displayDate(days[0])}/${days[0].getFullYear()} – ${displayDate(days[days.length - 1])}/${days[days.length - 1].getFullYear()} · ${days.length} ngày`
  const monthTitle = `THÁNG ${String(days[0].getMonth() + 1).padStart(2, '0')}/${days[0].getFullYear()}`

  useEffect(() => {
    if (!availableDepartments.length) return
    const preferred = preferredDepartment(user, availableDepartments)
    if (!availableDepartments.includes(department)) setDepartment(preferred)
  }, [availableDepartments, department, user])

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
    setPastePanelOpen(false)
    try {
      const start = isoDate(days[0])
      const end = isoDate(days[days.length - 1])
      const result = await scheduleRequest(`/v2/work-schedule?start=${start}&end=${end}&department=${department}`)
      const wanted = (result.employees || [])
        .filter((item) => item.employment_status !== 'Đã nghỉ việc')
        .sort((left, right) => {
          const leftOwn = String(left.username || '').toLowerCase() === ownUsername ? 0 : 1
          const rightOwn = String(right.username || '').toLowerCase() === ownUsername ? 0 : 1
          if (leftOwn !== rightOwn) return leftOwn - rightOwn
          return String(left.full_name || left.username || '').localeCompare(String(right.full_name || right.username || ''), 'vi')
        })
      setEmployees(wanted)
      const mapped = Object.fromEntries((result.rows || []).map((row) => [keyFor(row.employee_username, row.work_date), {
        shift_code: row.shift_code || '',
        overtime_shift: row.overtime_shift || '',
        start_time: String(row.start_time || '').slice(0, 5),
        end_time: String(row.end_time || '').slice(0, 5),
        overtime_start_time: String(row.overtime_start_time || '').slice(0, 5),
        overtime_end_time: String(row.overtime_end_time || '').slice(0, 5),
        note: row.note || '',
      }]))
      const definitions = result.shift_definitions || { quanly: {}, letan: {}, locker: {} }
      setShiftDefinitions(definitions)
      if (department !== 'quanly') {
        setShiftDrafts(Object.entries(definitions?.[department] || {}).map(([shift_code, spec]) => ({
          shift_code,
          start_time: spec?.start || '',
          end_time: spec?.end || '',
        })))
      } else {
        setShiftDrafts([])
      }
      setSaved(mapped)
      setDrafts(mapped)

      const own = wanted.find((item) => String(item.username || '').toLowerCase() === ownUsername)
      if (own) {
        const defaultDay = days.some((item) => isoDate(item) === todayIso) ? todayIso : isoDate(days[0])
        setSelectedCell({ username: own.username, day: defaultDay })
      } else {
        setSelectedCell(null)
      }
    } catch (error) {
      setNotice(error.message || 'Không tải được lịch làm việc.')
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { void load() }, [department, month]) // eslint-disable-line react-hooks/exhaustive-deps

  const setCell = (username, day, field, value) => {
    const key = keyFor(username, day)
    setDrafts((current) => {
      const next = { ...emptyCell(), ...(current[key] || {}), [field]: value }
      if (field === 'shift_code' && value === '') return { ...current, [key]: emptyCell() }
      if (field === 'shift_code' && value === 'Nghỉ') {
        next.overtime_shift = ''
        next.start_time = ''
        next.end_time = ''
        next.overtime_start_time = ''
        next.overtime_end_time = ''
      }
      if (department === 'quanly') {
        next.overtime_shift = ''
        next.overtime_start_time = ''
        next.overtime_end_time = ''
      } else {
        next.start_time = ''
        next.end_time = ''
      }
      if (department === 'locker') {
        next.overtime_start_time = ''
        next.overtime_end_time = ''
      }
      if (department === 'letan') next.overtime_shift = ''
      return { ...current, [key]: next }
    })
  }

  const resolveClipboard = async () => {
    let payload = clipboardCell
    try {
      const raw = await navigator.clipboard?.readText()
      if (raw?.startsWith('VERA_SCHEDULE:')) payload = JSON.parse(raw.slice('VERA_SCHEDULE:'.length))
    } catch {
      // Internal clipboard remains available when browser clipboard is blocked.
    }
    return payload
  }

  const copyCell = async (username, day) => {
    const key = keyFor(username, day)
    const payload = { department, value: { ...emptyCell(), ...(drafts[key] || {}) } }
    setClipboardCell(payload)
    setSelectedCell({ username, day })
    setPastePanelOpen(false)
    try {
      await navigator.clipboard?.writeText(`VERA_SCHEDULE:${JSON.stringify(payload)}`)
    } catch {
      // Internal clipboard remains available even when browser clipboard is blocked.
    }
    setNotice(`Đã sao chép ô ${day}. Chọn ô đích rồi bấm Dán ô để áp dụng 1 hoặc nhiều ngày liên tiếp.`)
  }

  const pasteCell = async (username, day) => {
    if (!canEdit) return
    const payload = await resolveClipboard()
    if (!payload?.value) {
      setNotice('Chưa có ô lịch nào được sao chép.')
      return
    }
    if (payload.department !== department) {
      setNotice(`Không thể dán dữ liệu ${DEPARTMENT_INFO[payload.department]?.label || payload.department} sang ${DEPARTMENT_INFO[department].label}.`)
      return
    }
    const key = keyFor(username, day)
    setClipboardCell(payload)
    setDrafts((current) => ({ ...current, [key]: { ...emptyCell(), ...payload.value } }))
    setSelectedCell({ username, day })
    setPastePanelOpen(false)
    setNotice(`Đã dán vào ngày ${day}. Bấm Lưu lịch để ghi chính thức.`)
  }

  const selectedCopy = () => {
    if (!selectedCell) return
    void copyCell(selectedCell.username, selectedCell.day)
  }

  const openPastePanel = async () => {
    if (!selectedCell || !canEdit) return
    const payload = await resolveClipboard()
    if (!payload?.value) {
      setNotice('Chưa có ô lịch nào được sao chép.')
      return
    }
    if (payload.department !== department) {
      setNotice(`Không thể dán dữ liệu ${DEPARTMENT_INFO[payload.department]?.label || payload.department} sang ${DEPARTMENT_INFO[department].label}.`)
      return
    }
    setClipboardCell(payload)
    setPasteEndDay(selectedCell.day)
    setPastePanelOpen(true)
  }

  const applyPasteRange = () => {
    if (!selectedCell || !clipboardCell?.value) return
    const startIndex = days.findIndex((item) => isoDate(item) === selectedCell.day)
    const endIndex = days.findIndex((item) => isoDate(item) === pasteEndDay)
    if (startIndex < 0 || endIndex < startIndex) {
      setNotice('Ngày kết thúc dán phải từ ngày đang chọn trở đi và nằm trong tháng đang xem.')
      return
    }
    const targetDays = days.slice(startIndex, endIndex + 1).map(isoDate)
    setDrafts((current) => {
      const next = { ...current }
      targetDays.forEach((day) => {
        next[keyFor(selectedCell.username, day)] = { ...emptyCell(), ...clipboardCell.value }
      })
      return next
    })
    setPastePanelOpen(false)
    setNotice(`Đã dán cùng một lịch cho ${targetDays.length} ngày liên tiếp (${targetDays[0]} → ${targetDays[targetDays.length - 1]}). Bấm Lưu lịch để ghi chính thức.`)
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
          if (department === 'letan' && Boolean(after.overtime_start_time) !== Boolean(after.overtime_end_time)) {
            throw new Error(`${employee.full_name || employee.username} · ${day}: tăng ca Lễ tân cần đủ giờ bắt đầu và giờ kết thúc.`)
          }
          rows.push({
            work_date: day,
            employee_username: employee.username,
            employee_name: employee.full_name || employee.username,
            department,
            shift_code: after.shift_code,
            overtime_shift: department === 'locker' ? (after.overtime_shift || '') : '',
            start_time: department === 'quanly' ? (after.start_time || '') : '',
            end_time: department === 'quanly' ? (after.end_time || '') : '',
            overtime_start_time: department === 'letan' ? (after.overtime_start_time || '') : '',
            overtime_end_time: department === 'letan' ? (after.overtime_end_time || '') : '',
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

  const changeShiftDraft = (index, field, value) => {
    setShiftDrafts((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item))
  }

  const addShiftDraft = () => {
    let number = shiftDrafts.length + 1
    let name = `Ca mới ${number}`
    const existing = new Set(shiftDrafts.map((item) => String(item.shift_code || '').toLowerCase()))
    while (existing.has(name.toLowerCase())) {
      number += 1
      name = `Ca mới ${number}`
    }
    setShiftDrafts((current) => [...current, { shift_code: name, start_time: '09:00', end_time: '17:00' }])
  }

  const removeShiftDraft = (index) => {
    if (shiftDrafts.length <= 1) {
      setNotice('Mỗi bộ phận phải còn ít nhất 1 ca làm việc.')
      return
    }
    setShiftDrafts((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  const saveShiftConfig = async () => {
    if (!canEdit || department === 'quanly') return
    setBusy(true)
    setNotice('')
    try {
      const normalized = shiftDrafts.map((item) => ({
        shift_code: String(item.shift_code || '').trim(),
        start_time: item.start_time || '',
        end_time: item.end_time || '',
      }))
      if (normalized.some((item) => !item.shift_code || !item.start_time || !item.end_time)) {
        throw new Error('Mỗi ca cần đủ Tên ca, Giờ bắt đầu và Giờ kết thúc.')
      }
      const result = await scheduleRequest('/v2/work-schedule/shifts', {
        method: 'PUT',
        body: JSON.stringify({ department, shifts: normalized }),
      })
      await load()
      setShiftEditorOpen(false)
      setNotice(result.message || 'Đã cập nhật cấu hình ca làm việc.')
    } catch (error) {
      setNotice(error.message || 'Không lưu được cấu hình ca.')
    } finally {
      setBusy(false)
    }
  }

  const lockerSummary = useMemo(() => {
    if (department !== 'locker') return {}
    return Object.fromEntries(days.map((date) => {
      const day = isoDate(date)
      const counts = { ca1: 0, ca2: 0, tc1: 0, tc2: 0 }
      employees.forEach((employee) => {
        const value = { ...emptyCell(), ...(drafts[keyFor(employee.username, day)] || {}) }
        if (value.shift_code === 'Ca 1') counts.ca1 += 1
        if (value.shift_code === 'Ca 2') counts.ca2 += 1
        if (value.overtime_shift === 'TC Ca 1') counts.tc1 += 1
        if (value.overtime_shift === 'TC Ca 2') counts.tc2 += 1
      })
      return [day, counts]
    }))
  }, [days, department, drafts, employees])

  const activeShiftDefinitions = shiftDefinitions?.[department] || {}

  if (!availableDepartments.length) {
    return <section className="work-schedule-page"><div className="warning-box">Tài khoản chưa được cấp quyền Lịch làm việc Quản lý, Lễ tân hoặc Locker.</div></section>
  }

  return (
    <section className="work-schedule-page">
      <style>{`
        .work-schedule-page{display:grid;gap:16px}.schedule-head{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}.schedule-title h2{margin:0}.schedule-title p{margin:4px 0 0;color:#64748b}.schedule-range{margin-top:7px;font-size:13px;font-weight:800;color:#1f513f}.schedule-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.schedule-month-picker{display:flex;align-items:center;gap:6px;border:1px solid #d7e2dd;border-radius:12px;padding:5px 7px;background:#fff}.schedule-month-picker input{border:0;background:transparent;font:inherit;font-weight:800;color:#25483b;min-width:142px}.schedule-icon-button{border:0;background:#eef5f2;color:#244a3a;border-radius:8px;width:34px;height:34px;display:grid;place-items:center}.schedule-legend{display:flex;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid #dfe8e5;border-radius:12px;background:#f8fbfa;font-size:13px}.schedule-scroll{overflow-x:auto;overflow-y:visible;border:1px solid #dfe8e5;border-radius:14px;background:#fff;max-width:100%;overscroll-behavior-x:contain}.schedule-grid{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}.schedule-grid th,.schedule-grid td{border-right:1px solid #e6ecea;border-bottom:1px solid #e6ecea;padding:6px;text-align:center;vertical-align:middle}.schedule-grid thead th{position:sticky;top:0;background:#eef6f3;z-index:4;min-width:116px}.schedule-grid thead tr:nth-child(2) th{top:35px}.schedule-grid thead th.employee-head{left:0;z-index:8;min-width:190px}.schedule-grid td.employee-cell,.schedule-grid tfoot td.summary-label{position:sticky;left:0;background:#fff;z-index:3;text-align:left;min-width:190px}.schedule-grid .month-head{height:35px;background:#dfeee8;font-weight:900;color:#244a3a}.schedule-grid .sunday{background:#fff6f2}.schedule-grid .today{box-shadow:inset 0 0 0 2px #bb8b34}.schedule-grid td.selected{box-shadow:inset 0 0 0 3px #245b47;background:#eff8f4}.schedule-grid tr.own-row td.employee-cell{background:#eef8f3}.schedule-grid tr.own-row td.employee-cell strong:after{content:' · Lịch của bạn';font-size:11px;color:#267051;font-weight:800}.schedule-cell{display:grid;gap:5px}.shift-select,.ot-select,.manager-status,.manager-time,.letan-ot-time{border:1px solid #d9e2df;border-radius:8px;background:#fff}.shift-select,.ot-select{width:108px;padding:5px;font-size:12px}.shift-select.ca1{background:#dff3cc}.shift-select.ca2{background:#fff8a8}.shift-select.off,.manager-status.off{background:#ffe0b8}.ot-select.active{font-weight:700}.manager-cell{display:grid;gap:5px;min-width:136px}.manager-status{width:126px;padding:5px;font-size:12px}.manager-time-row{display:grid;grid-template-columns:1fr 1fr;gap:4px}.manager-time{width:61px;min-width:0;padding:5px 3px;font-size:11px}.letan-overtime{display:grid;grid-template-columns:auto 1fr 1fr;gap:3px;align-items:center}.letan-overtime span{font-size:10px;font-weight:900;color:#80591c}.letan-ot-time{width:48px;min-width:0;padding:4px 1px;font-size:10px}.schedule-save,.schedule-copy-button,.schedule-config-button{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:9px 13px;font-weight:700}.schedule-save{background:#173329;color:white}.schedule-copy-button,.schedule-config-button{background:#eef5f2;color:#214538;border:1px solid #ccddd5}.schedule-save:disabled,.schedule-copy-button:disabled,.schedule-config-button:disabled{opacity:.5}.schedule-notice{padding:10px 12px;border-radius:10px;background:#edf7f3}.employee-role{display:block;color:#708079;font-size:12px;margin-top:2px}.schedule-help{font-size:12px;color:#66766f}.schedule-department-tabs{display:flex;gap:6px;flex-wrap:wrap}.schedule-department-tabs button{border:1px solid #d7e2dd;background:#fff;border-radius:10px;padding:8px 11px;font-weight:800;color:#4a5d55}.schedule-department-tabs button.active{background:#173329;color:#fff;border-color:#173329}.paste-range-panel,.shift-editor{display:grid;gap:10px;padding:12px;border:1px solid #d8e5df;border-radius:12px;background:#fbfdfc}.paste-range-panel{grid-template-columns:auto auto auto auto;align-items:end}.paste-range-panel label,.shift-editor label{display:grid;gap:4px;font-size:12px;font-weight:800;color:#40544c}.paste-range-panel input,.shift-editor input{border:1px solid #d5e0dc;border-radius:8px;padding:8px;background:#fff}.paste-range-panel button{height:36px}.shift-editor-head{display:flex;justify-content:space-between;gap:10px;align-items:center;flex-wrap:wrap}.shift-editor-rows{display:grid;gap:8px}.shift-editor-row{display:grid;grid-template-columns:minmax(140px,1fr) 110px 110px 42px;gap:8px;align-items:end}.shift-editor-row button{height:36px;border:1px solid #efd3d3;background:#fff4f4;color:#9b3636;border-radius:8px;display:grid;place-items:center}.shift-editor-actions{display:flex;gap:8px;justify-content:flex-end;flex-wrap:wrap}.locker-summary-row td{background:#f4f8f6;font-size:11px;font-weight:700}.schedule-grid tfoot td.summary-label{background:#e7f1ed;font-weight:900}.locker-summary-cell{display:grid;grid-template-columns:1fr 1fr;gap:3px;text-align:left;min-width:108px}.locker-summary-cell span{white-space:nowrap}.locker-summary-cell b{color:#173329}.shift-legend-item{display:inline-flex;gap:5px}.shift-legend-item strong{color:#173329}@media(max-width:700px){.schedule-title p{font-size:13px}.schedule-grid thead th.employee-head,.schedule-grid td.employee-cell,.schedule-grid tfoot td.summary-label{min-width:145px}.schedule-grid thead th{min-width:108px}.schedule-tools{width:100%}.schedule-copy-button,.schedule-save,.schedule-config-button{flex:1;justify-content:center}.schedule-month-picker{width:100%;justify-content:space-between}.paste-range-panel{grid-template-columns:1fr 1fr}.paste-range-panel button{width:100%}.shift-editor-row{grid-template-columns:1fr 1fr}.shift-editor-row label:first-child{grid-column:1/-1}.shift-editor-row button{align-self:end}}
      `}</style>

      <div className="schedule-head">
        <div className="schedule-title">
          <h2>Lịch làm việc</h2>
          <p>Sắp lịch từng ngày, không dùng chu kỳ. Có thể cuộn ngang để xem đầy đủ tất cả ngày trong tháng đã chọn.</p>
          <div className="schedule-range">{rangeLabel}</div>
        </div>
        <div className="schedule-tools">
          <div className="schedule-month-picker">
            <button type="button" className="schedule-icon-button" aria-label="Tháng trước" onClick={() => setMonth((value) => moveMonth(value, -1))}><ChevronLeft size={17}/></button>
            <CalendarDays size={17}/><input type="month" value={month} onChange={(event) => setMonth(event.target.value || currentMonthValue())} aria-label="Chọn tháng lịch làm việc" />
            <button type="button" className="schedule-icon-button" aria-label="Tháng sau" onClick={() => setMonth((value) => moveMonth(value, 1))}><ChevronRight size={17}/></button>
          </div>
          <button type="button" className="schedule-copy-button" onClick={selectedCopy} disabled={!selectedCell}><Copy size={16}/> Sao chép ô</button>
          <button type="button" className="schedule-copy-button" onClick={() => void openPastePanel()} disabled={!selectedCell || !canEdit}><ClipboardPaste size={16}/> Dán ô</button>
          {canEdit && department !== 'quanly' && <button type="button" className="schedule-config-button" onClick={() => setShiftEditorOpen((value) => !value)}><Settings2 size={16}/> Tạo / sửa ca</button>}
          {canEdit && <button type="button" className="schedule-save" onClick={saveChanges} disabled={busy || loading}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16} />} Lưu lịch</button>}
        </div>
      </div>

      <div className="schedule-department-tabs">
        {availableDepartments.map((item) => <button type="button" key={item} className={department === item ? 'active' : ''} onClick={() => { setDepartment(item); setShiftEditorOpen(false) }}>{DEPARTMENT_INFO[item].label}</button>)}
      </div>

      {department === 'quanly'
        ? <div className="schedule-legend"><strong>Quản lý</strong><span>Mỗi ngày nhập riêng Giờ bắt đầu → Giờ kết thúc.</span><span>Không áp dụng Ca 1/Ca 2.</span></div>
        : <div className="schedule-legend">
            <strong>{DEPARTMENT_INFO[department].label}</strong>
            {Object.entries(activeShiftDefinitions).map(([name, spec]) => <span className="shift-legend-item" key={name}><strong>{name}:</strong> {formatShiftTime(spec)}</span>)}
            {department === 'locker' ? <span>Tăng ca: TC Ca 1 / TC Ca 2</span> : <span>Tăng ca: nhập trực tiếp giờ bắt đầu → giờ kết thúc</span>}
          </div>}

      {shiftEditorOpen && canEdit && department !== 'quanly' && <div className="shift-editor">
        <div className="shift-editor-head"><div><strong>TẠO / CHỈNH SỬA CA · {DEPARTMENT_INFO[department].label}</strong><div className="schedule-help">Thay đổi ở đây sẽ được dùng cho các lịch mới. Nếu giờ kết thúc nhỏ hơn giờ bắt đầu, hệ thống hiểu là kết thúc vào hôm sau.</div></div><button type="button" className="schedule-config-button" onClick={addShiftDraft}><Plus size={15}/> Thêm ca</button></div>
        <div className="shift-editor-rows">{shiftDrafts.map((item, index) => <div className="shift-editor-row" key={`${index}-${item.shift_code}`}>
          <label>Tên ca<input value={item.shift_code} onChange={(event) => changeShiftDraft(index, 'shift_code', event.target.value)} /></label>
          <label>Bắt đầu<input type="time" value={item.start_time} onChange={(event) => changeShiftDraft(index, 'start_time', event.target.value)} /></label>
          <label>Kết thúc<input type="time" value={item.end_time} onChange={(event) => changeShiftDraft(index, 'end_time', event.target.value)} /></label>
          <button type="button" aria-label={`Xóa ${item.shift_code}`} onClick={() => removeShiftDraft(index)}><Trash2 size={15}/></button>
        </div>)}</div>
        <div className="shift-editor-actions"><button type="button" className="schedule-copy-button" onClick={() => setShiftEditorOpen(false)}>Hủy</button><button type="button" className="schedule-save" disabled={busy} onClick={() => void saveShiftConfig()}><Save size={15}/> Lưu cấu hình ca</button></div>
      </div>}

      <div className="schedule-help">Mặc định mở đúng bộ phận của tài khoản đang đăng nhập và đưa lịch của chính tài khoản đó lên đầu danh sách. Chọn một ô để Sao chép/Dán; Ctrl+C và Ctrl+V vẫn dán nhanh 1 ô.</div>
      {pastePanelOpen && selectedCell && <div className="paste-range-panel">
        <label>Nhân viên<input value={employees.find((item) => item.username === selectedCell.username)?.full_name || selectedCell.username} readOnly /></label>
        <label>Từ ngày<input type="date" value={selectedCell.day} readOnly /></label>
        <label>Đến ngày<input type="date" min={selectedCell.day} max={isoDate(days[days.length - 1])} value={pasteEndDay} onChange={(event) => setPasteEndDay(event.target.value)} /></label>
        <button type="button" className="schedule-save" onClick={applyPasteRange}><ClipboardPaste size={15}/> Áp dụng liên tiếp</button>
      </div>}
      {notice && <div className="schedule-notice">{notice}</div>}

      {loading ? <div className="page-loading"><LoaderCircle size={18} className="spin" /> Đang tải lịch…</div> : (
        <div className="schedule-scroll">
          <table className="schedule-grid">
            <thead>
              <tr><th className="employee-head" rowSpan="2">Tên nhân viên</th><th className="month-head" colSpan={days.length}>{monthTitle}</th></tr>
              <tr>{days.map((date) => {
                const day = isoDate(date)
                const classes = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : ''].filter(Boolean).join(' ')
                return <th key={day} className={classes}><div>{WEEKDAYS[date.getDay()]}</div><small>{displayDate(date)}</small></th>
              })}</tr>
            </thead>
            <tbody>{employees.map((employee) => {
              const isOwn = String(employee.username || '').toLowerCase() === ownUsername
              return <tr key={employee.username} className={isOwn ? 'own-row' : ''}>
                <td className="employee-cell"><strong>{employee.full_name || employee.username}</strong><span className="employee-role">{DEPARTMENT_INFO[department].label}</span></td>
                {days.map((date) => {
                  const day = isoDate(date)
                  const cellKey = keyFor(employee.username, day)
                  const value = { ...emptyCell(), ...(drafts[cellKey] || {}) }
                  const isSelected = selectedCell?.username === employee.username && selectedCell?.day === day
                  const tdClass = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : '', isSelected ? 'selected' : ''].filter(Boolean).join(' ')
                  const shiftClass = value.shift_code === 'Ca 1' ? 'ca1' : value.shift_code === 'Ca 2' ? 'ca2' : value.shift_code === 'Nghỉ' ? 'off' : ''
                  const configuredShiftNames = Object.keys(activeShiftDefinitions)
                  const shiftNames = value.shift_code && !['Nghỉ', 'Giờ làm'].includes(value.shift_code) && !configuredShiftNames.includes(value.shift_code)
                    ? [value.shift_code, ...configuredShiftNames]
                    : configuredShiftNames
                  return <td key={day} className={tdClass} tabIndex={0} onFocus={() => setSelectedCell({ username: employee.username, day })} onClick={() => setSelectedCell({ username: employee.username, day })} onKeyDown={(event) => handleCellKeyDown(event, employee.username, day)}>
                    {department === 'quanly' ? <div className="manager-cell">
                      <select className={`manager-status ${value.shift_code === 'Nghỉ' ? 'off' : ''}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
                        <option value="">—</option><option value="Giờ làm">Làm việc</option><option value="Nghỉ">Nghỉ</option>
                      </select>
                      {value.shift_code === 'Giờ làm' && <div className="manager-time-row"><input className="manager-time" type="time" value={value.start_time || ''} disabled={!canEdit} aria-label={`Giờ bắt đầu ${day}`} onChange={(event) => setCell(employee.username, day, 'start_time', event.target.value)} /><input className="manager-time" type="time" value={value.end_time || ''} disabled={!canEdit} aria-label={`Giờ kết thúc ${day}`} onChange={(event) => setCell(employee.username, day, 'end_time', event.target.value)} /></div>}
                    </div> : <div className="schedule-cell">
                      <select className={`shift-select ${shiftClass}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
                        <option value="">—</option>{shiftNames.map((shift) => <option key={shift} value={shift}>{shift}{!configuredShiftNames.includes(shift) ? ' (cũ)' : ''}</option>)}<option value="Nghỉ">Nghỉ</option>
                      </select>
                      {department === 'locker'
                        ? <select className={`ot-select ${value.overtime_shift ? 'active' : ''}`} value={value.overtime_shift || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(event) => setCell(employee.username, day, 'overtime_shift', event.target.value)}><option value="">Không TC</option><option>TC Ca 1</option><option>TC Ca 2</option></select>
                        : <div className="letan-overtime" title="Tăng ca Lễ tân: để trống cả hai ô nếu không tăng ca"><span>TC</span><input className="letan-ot-time" type="time" value={value.overtime_start_time || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} aria-label={`Tăng ca bắt đầu ${day}`} onChange={(event) => setCell(employee.username, day, 'overtime_start_time', event.target.value)} /><input className="letan-ot-time" type="time" value={value.overtime_end_time || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} aria-label={`Tăng ca kết thúc ${day}`} onChange={(event) => setCell(employee.username, day, 'overtime_end_time', event.target.value)} /></div>}
                    </div>}
                  </td>
                })}
              </tr>
            })}</tbody>
            {department === 'locker' && <tfoot><tr className="locker-summary-row"><td className="summary-label">TỔNG NHÂN SỰ</td>{days.map((date) => {
              const day = isoDate(date)
              const counts = lockerSummary[day] || { ca1: 0, ca2: 0, tc1: 0, tc2: 0 }
              return <td key={day}><div className="locker-summary-cell"><span>Ca 1: <b>{counts.ca1}</b></span><span>Ca 2: <b>{counts.ca2}</b></span><span>TC 1: <b>{counts.tc1}</b></span><span>TC 2: <b>{counts.tc2}</b></span></div></td>
            })}</tr></tfoot>}
          </table>
          {!employees.length && <div className="revenue-meta">Không có nhân viên đang hiển thị trong nhóm {DEPARTMENT_INFO[department].label}.</div>}
        </div>
      )}
    </section>
  )
}
