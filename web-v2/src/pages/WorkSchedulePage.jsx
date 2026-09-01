import {
  CalendarDays, ChevronLeft, ChevronRight, ClipboardPaste, Copy, LoaderCircle,
  PencilLine, Plus, Save, Settings2, Trash2,
} from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const WEEKDAYS = ['CN', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']
const WEEKDAYS_SHORT = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
const DEPARTMENTS = ['locker', 'letan', 'quanly']
const DEPARTMENT_PERMISSION = {
  locker: 'work_schedule_locker',
  letan: 'work_schedule_letan',
  quanly: 'work_schedule_quanly',
}
const DEPARTMENT_INFO = {
  locker: { label: 'Locker', mode: 'shift' },
  letan: { label: 'Lễ tân', mode: 'shift' },
  quanly: { label: 'Quản lý', mode: 'time' },
}
const RANGE_FILTERS = [
  ['today', 'Hôm nay'],
  ['week', 'Tuần này'],
  ['next_week', 'Tuần sau'],
  ['month', 'Tháng này'],
  ['next_month', 'Tháng sau'],
  ['custom', 'Tùy chỉnh'],
]

function atNoon(value = new Date()) {
  const date = new Date(value)
  date.setHours(12, 0, 0, 0)
  return date
}

function isoDate(date) {
  const y = date.getFullYear()
  const m = String(date.getMonth() + 1).padStart(2, '0')
  const d = String(date.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

function parseIsoDate(value) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/)
  if (!match) return null
  return new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]), 12, 0, 0, 0)
}

function displayDate(date) {
  return `${String(date.getDate()).padStart(2, '0')}/${String(date.getMonth() + 1).padStart(2, '0')}`
}

function displayFullDate(date) {
  return `${displayDate(date)}/${date.getFullYear()}`
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

function weekDays(base = new Date(), offsetWeeks = 0) {
  const start = atNoon(base)
  const offset = (start.getDay() + 6) % 7
  start.setDate(start.getDate() - offset + (offsetWeeks * 7))
  return Array.from({ length: 7 }, (_, index) => {
    const date = atNoon(start)
    date.setDate(start.getDate() + index)
    return date
  })
}

function daysBetween(startValue, endValue) {
  const start = parseIsoDate(startValue)
  const end = parseIsoDate(endValue)
  if (!start || !end || end < start) return []
  const result = []
  const cursor = atNoon(start)
  while (cursor <= end && result.length < 63) {
    result.push(atNoon(cursor))
    cursor.setDate(cursor.getDate() + 1)
  }
  return result
}

function preferredDepartment(user, available) {
  const role = String(user?.role || '').toLowerCase()
  return available.includes(role) ? role : (available[0] || 'locker')
}

function keyFor(username, day) { return `${username}__${day}` }

function systemName(employee) {
  return String(employee?.system_name || employee?.username || '').trim()
}

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

function timeMinutes(value) {
  const match = String(value || '').match(/^(\d{2}):(\d{2})$/)
  if (!match) return null
  return Number(match[1]) * 60 + Number(match[2])
}

function timeRangesOverlap(startA, endA, startB, endB) {
  const aStart = timeMinutes(startA)
  const aEndRaw = timeMinutes(endA)
  const bStart = timeMinutes(startB)
  const bEndRaw = timeMinutes(endB)
  if ([aStart, aEndRaw, bStart, bEndRaw].some((value) => value === null)) return false
  const aEnd = aEndRaw <= aStart ? aEndRaw + 1440 : aEndRaw
  const bEnd = bEndRaw <= bStart ? bEndRaw + 1440 : bEndRaw
  return [-1440, 0, 1440].some((offset) => {
    const shiftedStart = bStart + offset
    const shiftedEnd = bEnd + offset
    return Math.max(aStart, shiftedStart) < Math.min(aEnd, shiftedEnd)
  })
}

function compactCellLabel(value, department) {
  if (!value?.shift_code) return '—'
  if (value.shift_code === 'Nghỉ') return 'Nghỉ'
  if (department === 'quanly') return `${value.start_time || '—'}→${value.end_time || '—'}`
  let label = value.shift_code.replace(/^Ca\s+/i, 'C')
  if (department === 'locker' && value.overtime_shift) label += ` +${value.overtime_shift.replace(/^TC\s+Ca\s+/i, 'TC')}`
  if (department === 'letan' && value.overtime_start_time && value.overtime_end_time) label += ' +TC'
  return label
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
  const today = atNoon()
  const todayIso = isoDate(today)
  const [rangeMode, setRangeMode] = useState('week')
  const [month, setMonth] = useState(currentMonthValue())
  const [customStart, setCustomStart] = useState(todayIso)
  const [customEnd, setCustomEnd] = useState(todayIso)

  const days = useMemo(() => {
    const base = atNoon()
    if (rangeMode === 'today') return [base]
    if (rangeMode === 'week') return weekDays(base)
    if (rangeMode === 'next_week') return weekDays(base, 1)
    if (rangeMode === 'next_month') return monthDays(moveMonth(currentMonthValue(), 1))
    if (rangeMode === 'selected_month') return monthDays(month)
    if (rangeMode === 'custom') {
      const custom = daysBetween(customStart, customEnd)
      return custom.length ? custom : [base]
    }
    return monthDays(currentMonthValue())
  }, [customEnd, customStart, month, rangeMode])

  const rangeStart = isoDate(days[0])
  const rangeEnd = isoDate(days[days.length - 1])
  const rangeKey = `${rangeStart}_${rangeEnd}`
  const isWeekView = ['week', 'next_week'].includes(rangeMode) && days.length === 7

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
  const [highlightedEmployee, setHighlightedEmployee] = useState('')
  const [clipboardCell, setClipboardCell] = useState(null)
  const [pastePanelOpen, setPastePanelOpen] = useState(false)
  const [pasteEndDay, setPasteEndDay] = useState('')

  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const roleCanEdit = ['admin', 'quanly'].includes(role)
  const canEdit = roleCanEdit && availableDepartments.includes(department)
  const ownUsername = String(user?.employee_username || '').trim().toLowerCase()
  const rangeLabel = `${displayFullDate(days[0])} – ${displayFullDate(days[days.length - 1])} · ${days.length} ngày`
  const rangeTitle = days.length > 1 && days[0].getMonth() === days[days.length - 1].getMonth() && days[0].getFullYear() === days[days.length - 1].getFullYear()
    ? `THÁNG ${String(days[0].getMonth() + 1).padStart(2, '0')}/${days[0].getFullYear()}`
    : `${displayFullDate(days[0])} – ${displayFullDate(days[days.length - 1])}`

  useEffect(() => {
    if (!availableDepartments.length) return
    const preferred = preferredDepartment(user, availableDepartments)
    if (!availableDepartments.includes(department)) setDepartment(preferred)
  }, [availableDepartments, department, user])

  const selectRange = (mode) => {
    setRangeMode(mode)
    setPastePanelOpen(false)
    if (mode === 'month') setMonth(currentMonthValue())
    if (mode === 'next_month') setMonth(moveMonth(currentMonthValue(), 1))
  }

  const changeSelectedMonth = (value) => {
    const next = value || currentMonthValue()
    setMonth(next)
    setRangeMode('selected_month')
    setPastePanelOpen(false)
  }

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
      const result = await scheduleRequest(`/v2/work-schedule?start=${rangeStart}&end=${rangeEnd}&department=${department}`)
      const wanted = (result.employees || [])
        .filter((item) => item.employment_status !== 'Đã nghỉ việc')
        .sort((left, right) => {
          const leftOwn = String(left.username || '').toLowerCase() === ownUsername ? 0 : 1
          const rightOwn = String(right.username || '').toLowerCase() === ownUsername ? 0 : 1
          if (leftOwn !== rightOwn) return leftOwn - rightOwn
          return systemName(left).localeCompare(systemName(right), 'vi')
        })
      setEmployees(wanted)
      setHighlightedEmployee((current) => wanted.some((item) => item.username === current) ? current : '')
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
      setShiftDrafts(department === 'quanly' ? [] : Object.entries(definitions?.[department] || {}).map(([shift_code, spec]) => ({
        shift_code,
        start_time: spec?.start || '',
        end_time: spec?.end || '',
      })))
      setSaved(mapped)
      setDrafts(mapped)

      const own = wanted.find((item) => String(item.username || '').toLowerCase() === ownUsername)
      if (own) {
        const defaultDay = days.some((item) => isoDate(item) === todayIso) ? todayIso : rangeStart
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

  useEffect(() => { void load() }, [department, rangeKey]) // eslint-disable-line react-hooks/exhaustive-deps

  const renameSystemName = async (employee) => {
    if (!isAdmin) return
    const current = systemName(employee)
    const next = window.prompt('Tên hệ thống của nhân viên:', current)
    if (next === null) return
    const clean = next.trim().replace(/\s+/g, ' ')
    if (!clean || clean === current) return
    setBusy(true)
    setNotice('')
    try {
      await scheduleRequest(`/v2/staff/${encodeURIComponent(employee.username)}/system-name`, {
        method: 'PATCH',
        body: JSON.stringify({ system_name: clean }),
      })
      await load()
      setNotice(`Đã đổi tên hệ thống thành “${clean}”. Tài khoản đăng nhập không thay đổi.`)
    } catch (error) {
      setNotice(error.message || 'Không đổi được tên hệ thống.')
    } finally {
      setBusy(false)
    }
  }

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
    try { await navigator.clipboard?.writeText(`VERA_SCHEDULE:${JSON.stringify(payload)}`) } catch { /* internal clipboard remains */ }
    setNotice(`Đã sao chép lịch ngày ${day}. Chọn ngày đích rồi bấm Áp dụng cho ngày.`)
  }

  const pasteCell = async (username, day) => {
    if (!canEdit) return
    const payload = await resolveClipboard()
    if (!payload?.value) return setNotice('Chưa có ô lịch nào được sao chép.')
    if (payload.department !== department) return setNotice('Không thể áp dụng lịch giữa hai bộ phận khác nhau.')
    setClipboardCell(payload)
    setDrafts((current) => ({ ...current, [keyFor(username, day)]: { ...emptyCell(), ...payload.value } }))
    setSelectedCell({ username, day })
    setPastePanelOpen(false)
    setNotice(`Đã áp dụng lịch vào ngày ${day}. Bấm Lưu lịch để ghi chính thức.`)
  }

  const openPastePanel = async () => {
    if (!selectedCell || !canEdit) return
    const payload = await resolveClipboard()
    if (!payload?.value) return setNotice('Chưa có ô lịch nào được sao chép.')
    if (payload.department !== department) return setNotice('Không thể áp dụng lịch giữa hai bộ phận khác nhau.')
    setClipboardCell(payload)
    setPasteEndDay(selectedCell.day)
    setPastePanelOpen(true)
  }

  const applyPasteRange = () => {
    if (!selectedCell || !clipboardCell?.value) return
    const startIndex = days.findIndex((item) => isoDate(item) === selectedCell.day)
    const endIndex = days.findIndex((item) => isoDate(item) === pasteEndDay)
    if (startIndex < 0 || endIndex < startIndex) return setNotice('Ngày kết thúc phải từ ngày đang chọn trở đi và nằm trong khoảng đang xem.')
    const targetDays = days.slice(startIndex, endIndex + 1).map(isoDate)
    setDrafts((current) => {
      const next = { ...current }
      targetDays.forEach((day) => { next[keyFor(selectedCell.username, day)] = { ...emptyCell(), ...clipboardCell.value } })
      return next
    })
    setPastePanelOpen(false)
    setNotice(`Đã áp dụng lịch cho ${targetDays.length} ngày. Bấm Lưu lịch để ghi chính thức.`)
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
            throw new Error(`${systemName(employee)} · ${day}: cần đủ giờ bắt đầu và giờ kết thúc.`)
          }
          if (department === 'letan' && Boolean(after.overtime_start_time) !== Boolean(after.overtime_end_time)) {
            throw new Error(`${systemName(employee)} · ${day}: tăng ca Lễ tân cần đủ giờ bắt đầu và giờ kết thúc.`)
          }
          rows.push({
            work_date: day,
            employee_username: employee.username,
            employee_name: systemName(employee),
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

  const changeShiftDraft = (index, field, value) => setShiftDrafts((current) => current.map((item, itemIndex) => itemIndex === index ? { ...item, [field]: value } : item))

  const addShiftDraft = () => {
    let number = shiftDrafts.length + 1
    let name = `Ca mới ${number}`
    const existing = new Set(shiftDrafts.map((item) => String(item.shift_code || '').toLowerCase()))
    while (existing.has(name.toLowerCase())) { number += 1; name = `Ca mới ${number}` }
    setShiftDrafts((current) => [...current, { shift_code: name, start_time: '09:00', end_time: '17:00' }])
  }

  const removeShiftDraft = (index) => {
    if (shiftDrafts.length <= 1) return setNotice('Mỗi bộ phận phải còn ít nhất 1 ca làm việc.')
    setShiftDrafts((current) => current.filter((_, itemIndex) => itemIndex !== index))
  }

  const saveShiftConfig = async () => {
    if (!canEdit || department === 'quanly') return
    setBusy(true)
    setNotice('')
    try {
      const shifts = shiftDrafts.map((item) => ({
        shift_code: String(item.shift_code || '').trim(),
        start_time: item.start_time || '',
        end_time: item.end_time || '',
      }))
      if (shifts.some((item) => !item.shift_code || !item.start_time || !item.end_time)) throw new Error('Mỗi ca cần đủ Tên ca, Giờ bắt đầu và Giờ kết thúc.')
      const result = await scheduleRequest('/v2/work-schedule/shifts', { method: 'PUT', body: JSON.stringify({ department, shifts }) })
      await load()
      setShiftEditorOpen(false)
      setNotice(result.message || 'Đã cập nhật cấu hình ca làm việc.')
    } catch (error) {
      setNotice(error.message || 'Không lưu được cấu hình ca.')
    } finally {
      setBusy(false)
    }
  }

  const activeShiftDefinitions = shiftDefinitions?.[department] || {}
  const configuredShiftNames = Object.keys(activeShiftDefinitions)

  const shiftSummary = useMemo(() => {
    if (department === 'quanly') return {}
    const definitions = shiftDefinitions?.[department] || {}
    const shiftNames = Object.keys(definitions)
    return Object.fromEntries(days.map((date) => {
      const day = isoDate(date)
      const counts = Object.fromEntries(shiftNames.map((shift) => [shift, { regular: 0, overtime: 0, total: 0 }]))
      employees.forEach((employee) => {
        const value = { ...emptyCell(), ...(drafts[keyFor(employee.username, day)] || {}) }
        if (counts[value.shift_code]) counts[value.shift_code].regular += 1
        if (department === 'locker') {
          const overtimeTarget = String(value.overtime_shift || '').replace(/^TC\s+/i, '')
          if (overtimeTarget && counts[overtimeTarget]) counts[overtimeTarget].overtime += 1
        } else if (value.overtime_start_time && value.overtime_end_time) {
          shiftNames.forEach((shift) => {
            const spec = definitions[shift] || {}
            if (timeRangesOverlap(spec.start, spec.end, value.overtime_start_time, value.overtime_end_time)) counts[shift].overtime += 1
          })
        }
      })
      Object.values(counts).forEach((item) => { item.total = item.regular + item.overtime })
      return [day, counts]
    }))
  }, [days, department, drafts, employees, shiftDefinitions])

  const editorFor = (employee, day, value) => {
    const shiftClass = value.shift_code === 'Ca 1' ? 'ca1' : value.shift_code === 'Ca 2' ? 'ca2' : value.shift_code === 'Nghỉ' ? 'off' : ''
    const shiftNames = value.shift_code && !['Nghỉ', 'Giờ làm'].includes(value.shift_code) && !configuredShiftNames.includes(value.shift_code)
      ? [value.shift_code, ...configuredShiftNames] : configuredShiftNames

    if (department === 'quanly') {
      return <div className="manager-cell">
        <select className={`manager-status ${value.shift_code === 'Nghỉ' ? 'off' : ''}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
          <option value="">—</option><option value="Giờ làm">Làm việc</option><option value="Nghỉ">Nghỉ</option>
        </select>
        {value.shift_code === 'Giờ làm' && <div className="manager-time-row">
          <input className="manager-time" type="time" value={value.start_time || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'start_time', event.target.value)} />
          <input className="manager-time" type="time" value={value.end_time || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'end_time', event.target.value)} />
        </div>}
      </div>
    }

    return <div className="schedule-cell">
      <select className={`shift-select ${shiftClass}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
        <option value="">—</option>
        {shiftNames.map((shift) => <option key={shift} value={shift}>{shift}{!configuredShiftNames.includes(shift) ? ' (cũ)' : ''}</option>)}
        <option value="Nghỉ">Nghỉ</option>
      </select>
      {department === 'locker'
        ? <select className={`ot-select ${value.overtime_shift ? 'active' : ''}`} value={value.overtime_shift || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(event) => setCell(employee.username, day, 'overtime_shift', event.target.value)}>
            <option value="">Không TC</option><option>TC Ca 1</option><option>TC Ca 2</option>
          </select>
        : <div className="letan-overtime"><span>TC</span>
            <input className="letan-ot-time" type="time" value={value.overtime_start_time || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(event) => setCell(employee.username, day, 'overtime_start_time', event.target.value)} />
            <input className="letan-ot-time" type="time" value={value.overtime_end_time || ''} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(event) => setCell(employee.username, day, 'overtime_end_time', event.target.value)} />
          </div>}
    </div>
  }

  const selectedEmployee = employees.find((item) => item.username === selectedCell?.username)
  const selectedValue = selectedCell ? { ...emptyCell(), ...(drafts[keyFor(selectedCell.username, selectedCell.day)] || {}) } : null

  if (!availableDepartments.length) return <section className="work-schedule-page"><div className="warning-box">Tài khoản chưa được cấp quyền Lịch làm việc.</div></section>

  return <section className="work-schedule-page">
    <style>{`
      .work-schedule-page{display:grid;gap:14px}.schedule-head{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}.schedule-title h2{margin:0}.schedule-range{margin-top:7px;font-size:13px;font-weight:800;color:#1f513f}.schedule-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.schedule-month-picker{display:flex;align-items:center;gap:6px;border:1px solid #d7e2dd;border-radius:12px;padding:5px 7px;background:#fff}.schedule-month-picker input{border:0;background:transparent;font:inherit;font-weight:800;color:#25483b;min-width:142px}.schedule-icon-button{border:0;background:#eef5f2;color:#244a3a;border-radius:8px;width:34px;height:34px;display:grid;place-items:center}.schedule-filter-bar{display:flex;gap:6px;flex-wrap:wrap}.schedule-filter-bar button{border:1px solid #d6e2dd;background:#fff;border-radius:999px;padding:7px 11px;font-weight:800;color:#466057}.schedule-filter-bar button.active{background:#173329;border-color:#173329;color:#fff}.schedule-custom-range{display:inline-flex;gap:7px;align-items:center;width:max-content;max-width:100%}.schedule-custom-range input{border:1px solid #d6e2dd;border-radius:9px;padding:7px;width:170px;min-width:0}.schedule-department-tabs{display:flex;gap:6px;flex-wrap:wrap}.schedule-department-tabs button{border:1px solid #d7e2dd;background:#fff;border-radius:10px;padding:8px 11px;font-weight:800;color:#4a5d55}.schedule-department-tabs button.active{background:#173329;color:#fff;border-color:#173329}.schedule-legend{display:flex;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid #dfe8e5;border-radius:12px;background:#f8fbfa;font-size:13px}.schedule-scroll{overflow-x:auto;border:1px solid #dfe8e5;border-radius:14px;background:#fff;max-width:100%}.schedule-grid{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}.schedule-grid th,.schedule-grid td{border-right:1px solid #e6ecea;border-bottom:1px solid #e6ecea;padding:6px;text-align:center;vertical-align:middle}.schedule-grid thead th{position:sticky;top:0;background:#eef6f3;z-index:4;min-width:116px}.schedule-grid thead tr:nth-child(2) th{top:35px}.schedule-grid thead th.employee-head{left:0;z-index:8;min-width:170px}.schedule-grid td.employee-cell,.schedule-grid tfoot td.summary-label{position:sticky;left:0;background:#fff;z-index:3;text-align:left;min-width:170px}.schedule-grid .month-head{height:35px;background:#dfeee8;font-weight:900;color:#244a3a}.schedule-grid .sunday{background:#fff6f2}.schedule-grid .today{box-shadow:inset 0 0 0 2px #bb8b34}.schedule-grid td.selected{box-shadow:inset 0 0 0 3px #245b47;background:#eff8f4}.schedule-grid tr.own-row td.employee-cell{background:#eef8f3}.schedule-grid tr.own-row td.employee-cell strong:after{content:' · Lịch của bạn';font-size:11px;color:#267051}.employee-name-line{display:flex;gap:5px;align-items:center}.employee-highlight-button{border:0;background:transparent;color:inherit;padding:4px 5px;margin:-4px -5px;border-radius:7px;text-align:left;cursor:pointer}.employee-highlight-button.active{background:#1f6b4d;color:#fff}.schedule-grid th.employee-work-day{background:#ccebdc;color:#155b3e;box-shadow:inset 0 -3px 0 #1f7a54}.schedule-grid td.employee-work-day{background:#e2f6eb!important;outline:3px solid #2b8a61;outline-offset:-3px}.system-name-edit{border:0;background:transparent;color:#5b7168;padding:2px;display:grid;place-items:center}.employee-role{display:block;color:#708079;font-size:11px;margin-top:2px}.schedule-cell{display:grid;gap:5px}.shift-select,.ot-select,.manager-status,.manager-time,.letan-ot-time{border:1px solid #d9e2df;border-radius:8px;background:#fff}.shift-select,.ot-select{width:108px;padding:5px;font-size:12px}.shift-select.ca1{background:#dff3cc}.shift-select.ca2{background:#fff8a8}.shift-select.off,.manager-status.off{background:#ffe0b8}.manager-cell{display:grid;gap:5px;min-width:136px}.manager-status{width:126px;padding:5px;font-size:12px}.manager-time-row{display:grid;grid-template-columns:1fr 1fr;gap:4px}.manager-time{width:61px;padding:5px 3px;font-size:11px}.letan-overtime{display:grid;grid-template-columns:auto 1fr 1fr;gap:3px;align-items:center}.letan-overtime span{font-size:10px;font-weight:900;color:#80591c}.letan-ot-time{width:48px;padding:4px 1px;font-size:10px}.schedule-save,.schedule-copy-button,.schedule-config-button{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:9px 13px;font-weight:700}.schedule-save{background:#173329;color:white}.schedule-copy-button,.schedule-config-button{background:#eef5f2;color:#214538;border:1px solid #ccddd5}.schedule-save:disabled,.schedule-copy-button:disabled,.schedule-config-button:disabled{opacity:.5}.schedule-notice{padding:10px 12px;border-radius:10px;background:#edf7f3}.paste-range-panel,.shift-editor{display:grid;gap:10px;padding:12px;border:1px solid #d8e5df;border-radius:12px;background:#fbfdfc}.paste-range-panel{grid-template-columns:auto auto auto auto;align-items:end}.paste-range-panel label,.shift-editor label{display:grid;gap:4px;font-size:12px;font-weight:800}.paste-range-panel input,.shift-editor input{border:1px solid #d5e0dc;border-radius:8px;padding:8px;background:#fff}.shift-editor-rows{display:grid;gap:8px}.shift-editor-row{display:grid;grid-template-columns:minmax(140px,1fr) 110px 110px 42px;gap:8px;align-items:end}.shift-editor-row button{height:36px;border:1px solid #efd3d3;background:#fff4f4;color:#9b3636;border-radius:8px}.shift-editor-actions,.shift-editor-head{display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap}.schedule-grid tfoot td{background:#f4f8f6;font-size:11px;font-weight:700}.schedule-grid tfoot td.summary-label{background:#e7f1ed;font-weight:900}.shift-total-cell{display:grid;gap:2px;min-width:100px}.shift-total-cell b{font-size:15px;color:#173329}.shift-total-cell small{color:#6a7a73}.weekday-short,.mobile-cell-summary,.mobile-week-editor{display:none}
      @media(max-width:700px){.schedule-tools{width:100%}.schedule-copy-button,.schedule-save,.schedule-config-button{flex:1;justify-content:center}.schedule-month-picker{width:100%;justify-content:space-between}.schedule-filter-bar{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}.schedule-filter-bar button{padding:7px 2px;font-size:10px}.schedule-custom-range{display:grid;grid-template-columns:1fr 1fr;width:100%;max-width:100%}.schedule-custom-range input{min-width:0;width:100%}.paste-range-panel{grid-template-columns:1fr 1fr}.shift-editor-row{grid-template-columns:1fr 1fr}.shift-editor-row label:first-child{grid-column:1/-1}.schedule-scroll.week-view{overflow-x:hidden}.schedule-scroll.week-view .schedule-grid{min-width:0;width:100%;table-layout:fixed}.schedule-scroll.week-view .schedule-grid thead th{min-width:0;padding:3px 1px;font-size:9px}.schedule-scroll.week-view .weekday-full{display:none}.schedule-scroll.week-view .weekday-short{display:block}.schedule-scroll.week-view .schedule-grid thead th.employee-head,.schedule-scroll.week-view .schedule-grid td.employee-cell,.schedule-scroll.week-view .schedule-grid tfoot td.summary-label{width:72px;min-width:72px;max-width:72px;padding:3px;white-space:normal;word-break:break-word}.schedule-scroll.week-view .schedule-grid td{padding:2px 1px;min-width:0}.schedule-scroll.week-view .employee-cell strong{font-size:9px;line-height:1.1}.schedule-scroll.week-view .employee-role,.schedule-scroll.week-view tr.own-row td.employee-cell strong:after,.schedule-scroll.week-view .system-name-edit{display:none}.schedule-scroll.week-view .schedule-cell-editor{display:none}.schedule-scroll.week-view .mobile-cell-summary{display:block;font-size:9px;font-weight:900;line-height:1.1;color:#244a3a}.schedule-scroll.week-view .month-head{font-size:10px;height:28px}.schedule-scroll.week-view .schedule-grid thead tr:nth-child(2) th{top:28px}.schedule-scroll.week-view .shift-total-cell{min-width:0;font-size:8px}.schedule-scroll.week-view .shift-total-cell b{font-size:11px}.schedule-scroll.week-view .shift-total-cell small{font-size:7px}.mobile-week-editor{display:grid;gap:8px;padding:10px;border:1px solid #d5e3dd;border-radius:12px;background:#f8fbfa}.mobile-week-editor .shift-select,.mobile-week-editor .ot-select,.mobile-week-editor .manager-status,.mobile-week-editor .manager-time,.mobile-week-editor .letan-ot-time{width:100%}}
    `}</style>

    <div className="schedule-head">
      <div className="schedule-title"><h2>Lịch làm việc</h2><div className="schedule-range">{rangeLabel}</div></div>
      <div className="schedule-tools">
        <div className="schedule-month-picker">
          <button type="button" className="schedule-icon-button" onClick={() => { const next = moveMonth(month, -1); setMonth(next); setRangeMode('selected_month') }}><ChevronLeft size={17}/></button>
          <CalendarDays size={17}/><input type="month" value={month} onChange={(event) => changeSelectedMonth(event.target.value)} />
          <button type="button" className="schedule-icon-button" onClick={() => { const next = moveMonth(month, 1); setMonth(next); setRangeMode('selected_month') }}><ChevronRight size={17}/></button>
        </div>
        <button type="button" className="schedule-copy-button" onClick={() => selectedCell && void copyCell(selectedCell.username, selectedCell.day)} disabled={!selectedCell}><Copy size={16}/> Sao chép ô</button>
        <button type="button" className="schedule-copy-button" onClick={() => void openPastePanel()} disabled={!selectedCell || !canEdit}><ClipboardPaste size={16}/> Áp dụng cho ngày</button>
        {canEdit && department !== 'quanly' && <button type="button" className="schedule-config-button" onClick={() => setShiftEditorOpen((value) => !value)}><Settings2 size={16}/> Tạo / sửa ca</button>}
        {canEdit && <button type="button" className="schedule-save" onClick={saveChanges} disabled={busy || loading}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16}/>} Lưu lịch</button>}
      </div>
    </div>

    <div className="schedule-filter-bar">{RANGE_FILTERS.map(([mode, label]) => <button type="button" key={mode} className={rangeMode === mode ? 'active' : ''} onClick={() => selectRange(mode)}>{label}</button>)}</div>
    {rangeMode === 'custom' && <div className="schedule-custom-range">
      <input type="date" value={customStart} onChange={(event) => { const value = event.target.value; setCustomStart(value); if (customEnd < value) setCustomEnd(value) }} />
      <input type="date" min={customStart} value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} />
    </div>}

    <div className="schedule-department-tabs">{availableDepartments.map((item) => <button type="button" key={item} className={department === item ? 'active' : ''} onClick={() => { setDepartment(item); setShiftEditorOpen(false) }}>{DEPARTMENT_INFO[item].label}</button>)}</div>

    {department !== 'quanly' && <div className="schedule-legend"><strong>{DEPARTMENT_INFO[department].label}</strong>{Object.entries(activeShiftDefinitions).map(([name, spec]) => <span key={name}><strong>{name}:</strong> {formatShiftTime(spec)}</span>)}</div>}

    {shiftEditorOpen && canEdit && department !== 'quanly' && <div className="shift-editor">
      <div className="shift-editor-head"><strong>TẠO / CHỈNH SỬA CA · {DEPARTMENT_INFO[department].label}</strong><button type="button" className="schedule-config-button" onClick={addShiftDraft}><Plus size={15}/> Thêm ca</button></div>
      <div className="shift-editor-rows">{shiftDrafts.map((item, index) => <div className="shift-editor-row" key={`${index}-${item.shift_code}`}>
        <label>Tên ca<input value={item.shift_code} onChange={(event) => changeShiftDraft(index, 'shift_code', event.target.value)} /></label>
        <label>Bắt đầu<input type="time" value={item.start_time} onChange={(event) => changeShiftDraft(index, 'start_time', event.target.value)} /></label>
        <label>Kết thúc<input type="time" value={item.end_time} onChange={(event) => changeShiftDraft(index, 'end_time', event.target.value)} /></label>
        <button type="button" onClick={() => removeShiftDraft(index)}><Trash2 size={15}/></button>
      </div>)}</div>
      <div className="shift-editor-actions"><button type="button" className="schedule-copy-button" onClick={() => setShiftEditorOpen(false)}>Hủy</button><button type="button" className="schedule-save" onClick={() => void saveShiftConfig()}><Save size={15}/> Lưu cấu hình ca</button></div>
    </div>}

    {pastePanelOpen && selectedCell && <div className="paste-range-panel">
      <label>Nhân viên<input value={systemName(employees.find((item) => item.username === selectedCell.username)) || selectedCell.username} readOnly /></label>
      <label>Từ ngày<input type="date" value={selectedCell.day} readOnly /></label>
      <label>Đến ngày<input type="date" min={selectedCell.day} max={rangeEnd} value={pasteEndDay} onChange={(event) => setPasteEndDay(event.target.value)} /></label>
      <button type="button" className="schedule-save" onClick={applyPasteRange}><ClipboardPaste size={15}/> Áp dụng</button>
    </div>}
    {notice && <div className="schedule-notice">{notice}</div>}

    {isWeekView && selectedCell && selectedEmployee && selectedValue && canEdit && <div className="mobile-week-editor"><strong>{systemName(selectedEmployee)} · {selectedCell.day}</strong>{editorFor(selectedEmployee, selectedCell.day, selectedValue)}</div>}

    {loading ? <div className="page-loading"><LoaderCircle size={18} className="spin" /> Đang tải lịch…</div> : <div className={`schedule-scroll ${isWeekView ? 'week-view' : ''}`}>
      <table className="schedule-grid">
        <thead><tr><th className="employee-head" rowSpan="2">Tên nhân viên</th><th className="month-head" colSpan={days.length}>{rangeTitle}</th></tr><tr>{days.map((date) => {
          const day = isoDate(date)
          const classes = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : ''].filter(Boolean).join(' ')
          const highlightedValue = highlightedEmployee ? { ...emptyCell(), ...(drafts[keyFor(highlightedEmployee, day)] || {}) } : null
          const isEmployeeWorkDay = Boolean(highlightedValue?.shift_code && highlightedValue.shift_code !== 'Nghỉ')
          return <th key={day} className={[classes, isEmployeeWorkDay ? 'employee-work-day' : ''].filter(Boolean).join(' ')}><div className="weekday-full">{WEEKDAYS[date.getDay()]}</div><div className="weekday-short">{WEEKDAYS_SHORT[date.getDay()]}</div><small>{displayDate(date)}</small></th>
        })}</tr></thead>
        <tbody>{employees.map((employee) => {
          const isOwn = String(employee.username || '').toLowerCase() === ownUsername
          const isHighlightedEmployee = highlightedEmployee === employee.username
          return <tr key={employee.username} className={isOwn ? 'own-row' : ''}><td className="employee-cell"><div className="employee-name-line"><button type="button" className={`employee-highlight-button ${isHighlightedEmployee ? 'active' : ''}`.trim()} aria-pressed={isHighlightedEmployee} title="Highlight các ngày nhân viên làm việc" onClick={() => setHighlightedEmployee((current) => current === employee.username ? '' : employee.username)}><strong>{systemName(employee)}</strong></button>{isAdmin && <button type="button" className="system-name-edit" title="Đổi tên hệ thống" onClick={() => void renameSystemName(employee)}><PencilLine size={13}/></button>}</div><span className="employee-role">{DEPARTMENT_INFO[department].label}</span></td>{days.map((date) => {
            const day = isoDate(date)
            const value = { ...emptyCell(), ...(drafts[keyFor(employee.username, day)] || {}) }
            const isSelected = selectedCell?.username === employee.username && selectedCell?.day === day
            const isEmployeeWorkDay = isHighlightedEmployee && Boolean(value.shift_code && value.shift_code !== 'Nghỉ')
            const tdClass = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : '', isSelected ? 'selected' : '', isEmployeeWorkDay ? 'employee-work-day' : ''].filter(Boolean).join(' ')
            return <td key={day} className={tdClass} tabIndex={0} onFocus={() => setSelectedCell({ username: employee.username, day })} onClick={() => setSelectedCell({ username: employee.username, day })} onKeyDown={(event) => handleCellKeyDown(event, employee.username, day)}><div className="schedule-cell-editor">{editorFor(employee, day, value)}</div><div className="mobile-cell-summary">{compactCellLabel(value, department)}</div></td>
          })}</tr>
        })}</tbody>
        {department !== 'quanly' && configuredShiftNames.length > 0 && <tfoot>{configuredShiftNames.map((shift) => <tr key={`summary-${shift}`}><td className="summary-label">Tổng NV · {shift}</td>{days.map((date) => {
          const day = isoDate(date)
          const counts = shiftSummary?.[day]?.[shift] || { regular: 0, overtime: 0, total: 0 }
          return <td key={`${shift}-${day}`}><div className="shift-total-cell"><b>{counts.total}</b><small>{counts.regular} chính + {counts.overtime} TC</small></div></td>
        })}</tr>)}</tfoot>}
      </table>
      {!employees.length && <div className="revenue-meta">Không có nhân viên đang hiển thị trong nhóm {DEPARTMENT_INFO[department].label}.</div>}
    </div>}
  </section>
}
