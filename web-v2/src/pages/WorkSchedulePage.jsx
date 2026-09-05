import {
  CalendarDays, Camera, ChevronLeft, ChevronRight, ClipboardPaste, Copy, Download, LoaderCircle,
  PencilLine, Plus, Save, Settings2, Trash2, Upload,
} from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { getCurrentSession } from '../lib/supabase'
import VeraDateInput from '../components/VeraDateInput'

const API_BASE = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const WEEKDAYS = ['CN', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7']
const WEEKDAYS_SHORT = ['CN', 'T2', 'T3', 'T4', 'T5', 'T6', 'T7']
const DEPARTMENTS = ['locker', 'letan', 'tapvu', 'quanly']
const DEPARTMENT_PERMISSION = {
  locker: 'work_schedule_locker',
  letan: 'work_schedule_letan',
  tapvu: 'work_schedule_tapvu',
  quanly: 'work_schedule_quanly',
}
const DEPARTMENT_INFO = {
  locker: { label: 'Locker', mode: 'shift' },
  letan: { label: 'Lễ tân', mode: 'shift' },
  tapvu: { label: 'Tạp vụ', mode: 'shift' },
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

function monthRange(monthValue) {
  const values = monthDays(monthValue)
  return { start: isoDate(values[0]), end: isoDate(values[values.length - 1]) }
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
    combo_sold: false, combo_sale_date: '', combo_customer_name: '',
    combo_customer_phone: '', combo_ticket: '', combo_note: '',
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

function durationHours(start, end) {
  const startMinutes = timeMinutes(start)
  const endRaw = timeMinutes(end)
  if (startMinutes === null || endRaw === null || startMinutes === endRaw) return 0
  const endMinutes = endRaw <= startMinutes ? endRaw + 1440 : endRaw
  return (endMinutes - startMinutes) / 60
}

function overtimeMode(value) {
  if (value?.overtime_shift === 'TC Ca 1' || value?.overtime_shift === 'TC Ca 2') return value.overtime_shift
  if (value?.overtime_shift === 'Từ giờ tới giờ' || value?.overtime_start_time || value?.overtime_end_time) return 'Từ giờ tới giờ'
  return ''
}

function workShiftBucket(value) {
  if (value?.shift_code === 'Ca 1' || value?.shift_code === 'Ca 2') return value.shift_code
  if (value?.shift_code !== 'Giờ làm') return ''
  const start = timeMinutes(value.start_time)
  return start === null ? '' : start < 12 * 60 ? 'Ca 1' : 'Ca 2'
}

function overtimeHours(value, definitions) {
  const mode = overtimeMode(value)
  if (mode === 'Từ giờ tới giờ') return durationHours(value.overtime_start_time, value.overtime_end_time)
  if (mode === 'TC Ca 1' || mode === 'TC Ca 2') {
    const spec = definitions?.[mode.replace(/^TC\s+/, '')]
    return spec ? durationHours(spec.start, spec.end) : 8
  }
  return 0
}

function compactCellLabel(value, department) {
  if (!value?.shift_code) return '—'
  if (value.shift_code === 'Nghỉ') return 'Nghỉ'
  let label = department === 'quanly' ? `${value.start_time || '—'}→${value.end_time || '—'}` : value.shift_code.replace(/^Ca\s+/i, 'C')
  const overtime = overtimeMode(value)
  if (overtime === 'TC Ca 1' || overtime === 'TC Ca 2') label += ` +${overtime.replace(/^TC\s+Ca\s+/i, 'TC')}`
  if (overtime === 'Từ giờ tới giờ') label += ' +TC'
  return label
}

function canvasToPngBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob((blob) => blob ? resolve(blob) : reject(new Error('Không tạo được ảnh PNG.')), 'image/png')
  })
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

async function scheduleFileRequest(path, options = {}) {
  if (!API_BASE) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${API_BASE}${path}`, { ...options, headers })
  if (!response.ok) {
    const payload = await response.json().catch(() => ({}))
    throw new Error(payload?.detail || payload?.message || 'Không xử lý được file lịch làm việc.')
  }
  return options.download ? response.blob() : response.json()
}

function saleDateLabel(value) {
  const parsed = parseIsoDate(value)
  return parsed ? displayFullDate(parsed) : (value || '—')
}

function ComboEmployeeTable({ employee, rows, defaultDate, canEdit, busy, onSave, onDelete }) {
  const emptyDraft = () => ({ sale_date: defaultDate, customer_name: '', customer_phone: '', combo_ticket: '', note: '' })
  const [draft, setDraft] = useState(emptyDraft)
  const [editingId, setEditingId] = useState('')

  const reset = () => {
    setDraft(emptyDraft())
    setEditingId('')
  }

  const beginEdit = (sale) => {
    setDraft({
      sale_date: sale.sale_date || defaultDate,
      customer_name: sale.customer_name || '',
      customer_phone: sale.customer_phone || '',
      combo_ticket: sale.combo_ticket || '',
      note: sale.note || '',
    })
    setEditingId(sale.id)
  }

  const submit = async () => {
    const saved = await onSave(employee, draft, editingId)
    if (saved) reset()
  }

  return <section className="combo-employee-card">
    <div className="combo-employee-title">
      <strong>BẢNG CỦA {systemName(employee).toUpperCase()}</strong>
      <span>{rows.length.toLocaleString('vi-VN')} lượt trong tháng</span>
    </div>
    {canEdit && <div className="combo-sale-fields">
      <label>Ngày bán<VeraDateInput aria-label="Ngày bán" value={draft.sale_date} onChange={(event) => setDraft({ ...draft, sale_date: event.target.value })} /></label>
      <label>Tên khách hàng<input value={draft.customer_name} onChange={(event) => setDraft({ ...draft, customer_name: event.target.value })} /></label>
      <label>Số điện thoại<input type="tel" inputMode="tel" value={draft.customer_phone} onChange={(event) => setDraft({ ...draft, customer_phone: event.target.value })} /></label>
      <label>Vé combo<input value={draft.combo_ticket} onChange={(event) => setDraft({ ...draft, combo_ticket: event.target.value })} /></label>
      <label>Ghi chú<input value={draft.note} onChange={(event) => setDraft({ ...draft, note: event.target.value })} /></label>
      <div className="combo-form-actions">
        {editingId && <button type="button" className="schedule-copy-button" disabled={busy} onClick={reset}>Hủy sửa</button>}
        <button type="button" className="schedule-save" disabled={busy} onClick={() => void submit()}>{editingId ? <Save size={15}/> : <Plus size={15}/>} {editingId ? 'Lưu sửa' : 'Thêm'}</button>
      </div>
    </div>}
    <div className="schedule-scroll">
      <table className="combo-sale-table">
        <thead><tr><th>Ngày bán</th><th>Tên khách hàng</th><th>Số điện thoại</th><th>Vé combo</th><th>Ghi chú</th>{canEdit && <th>Thao tác</th>}</tr></thead>
        <tbody>{rows.map((sale) => <tr key={sale.id}>
          <td>{saleDateLabel(sale.sale_date)}</td><td>{sale.customer_name}</td><td>{sale.customer_phone}</td><td>{sale.combo_ticket}</td><td>{sale.note}</td>
          {canEdit && <td><div className="combo-row-actions"><button type="button" className="combo-edit" title="Sửa" aria-label={`Sửa combo ${sale.customer_name}`} onClick={() => beginEdit(sale)}><PencilLine size={14}/></button><button type="button" className="combo-delete" title="Xóa" aria-label={`Xóa combo ${sale.customer_name}`} onClick={() => void onDelete(sale)}><Trash2 size={14}/></button></div></td>}
        </tr>)}</tbody>
      </table>
      {!rows.length && <div className="revenue-meta">Chưa có dữ liệu bán combo của nhân viên này trong tháng.</div>}
    </div>
  </section>
}

export default function WorkSchedulePage({ user }) {
  const today = atNoon()
  const todayIso = isoDate(today)
  const yesterday = atNoon(today)
  yesterday.setDate(yesterday.getDate() - 1)
  const yesterdayIso = isoDate(yesterday)
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
  const isMonthView = ['month', 'next_month', 'selected_month'].includes(rangeMode) && days.length >= 28

  const availableDepartments = useMemo(() => {
    if (String(user?.role || '').toLowerCase() === 'admin') return DEPARTMENTS
    return DEPARTMENTS.filter((item) => user?.permissions?.[DEPARTMENT_PERMISSION[item]] === true)
  }, [user?.permissions, user?.role])

  const [department, setDepartment] = useState(() => preferredDepartment(user, availableDepartments))
  const [employees, setEmployees] = useState([])
  const [saved, setSaved] = useState({})
  const [drafts, setDrafts] = useState({})
  const [monthlyRows, setMonthlyRows] = useState([])
  const [comboSales, setComboSales] = useState([])
  const comboFileInputRef = useRef(null)
  const scheduleFileInputRef = useRef(null)
  const autoSaveTimerRef = useRef(null)
  const autoSaveAttemptRef = useRef('')
  const importedAwaitingManualSaveRef = useRef(false)
  const [shiftDefinitions, setShiftDefinitions] = useState({ quanly: {}, letan: {}, locker: {}, tapvu: {} })
  const [shiftDrafts, setShiftDrafts] = useState([])
  const [shiftEditorOpen, setShiftEditorOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState('')
  const [selectedCell, setSelectedCell] = useState(null)
  const [highlightedEmployee, setHighlightedEmployee] = useState('')
  const [highlightedTotal, setHighlightedTotal] = useState(null)
  const [clipboardCell, setClipboardCell] = useState(null)
  const [pastePanelOpen, setPastePanelOpen] = useState(false)
  const [pasteEndDay, setPasteEndDay] = useState('')
  const [autoSaveState, setAutoSaveState] = useState('saved')
  const [captureBusy, setCaptureBusy] = useState(false)

  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const roleCanEdit = ['admin', 'quanly'].includes(role)
  const canEdit = roleCanEdit && availableDepartments.includes(department)
  const canEditCombo = ['admin', 'quanly', 'letan'].includes(role) && availableDepartments.includes(department)
  const ownUsername = String(user?.employee_username || '').trim().toLowerCase()
  const comboDefaultDate = month === currentMonthValue() ? todayIso : `${month}-01`
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
      const statisticsRange = monthRange(month)
      const currentPath = `/v2/work-schedule?start=${rangeStart}&end=${rangeEnd}&department=${department}`
      const statisticsPath = `/v2/work-schedule?start=${statisticsRange.start}&end=${statisticsRange.end}&department=${department}`
      const [result, statisticsResult] = await Promise.all([
        scheduleRequest(currentPath),
        statisticsPath === currentPath ? Promise.resolve(null) : scheduleRequest(statisticsPath),
      ])
      const monthlyResult = statisticsResult || result
      const wanted = (result.employees || [])
        .filter((item) => item.employment_status !== 'Đã nghỉ việc')
        .sort((left, right) => {
          const leftOwn = String(left.username || '').toLowerCase() === ownUsername ? 0 : 1
          const rightOwn = String(right.username || '').toLowerCase() === ownUsername ? 0 : 1
          if (leftOwn !== rightOwn) return leftOwn - rightOwn
          return systemName(left).localeCompare(systemName(right), 'vi')
        })
      setEmployees(wanted)
      setMonthlyRows(monthlyResult.rows || [])
      if (['quanly', 'letan'].includes(department)) {
        const comboResult = await scheduleRequest(`/v2/work-schedule/combo-sales?start=${statisticsRange.start}&end=${statisticsRange.end}&department=${department}`)
        setComboSales(comboResult.rows || [])
      } else {
        setComboSales([])
      }
      setHighlightedEmployee((current) => wanted.some((item) => item.username === current) ? current : '')
      setHighlightedTotal(null)
      const mapped = Object.fromEntries((result.rows || []).map((row) => [keyFor(row.employee_username, row.work_date), {
        shift_code: row.shift_code || '',
        overtime_shift: row.overtime_shift || '',
        start_time: String(row.start_time || '').slice(0, 5),
        end_time: String(row.end_time || '').slice(0, 5),
        overtime_start_time: String(row.overtime_start_time || '').slice(0, 5),
        overtime_end_time: String(row.overtime_end_time || '').slice(0, 5),
        note: row.note || '',
        combo_sold: Boolean(row.combo_sold),
        combo_sale_date: row.combo_sale_date || '',
        combo_customer_name: row.combo_customer_name || '',
        combo_customer_phone: row.combo_customer_phone || '',
        combo_ticket: row.combo_ticket || '',
        combo_note: row.combo_note || '',
      }]))
      const definitions = result.shift_definitions || { quanly: {}, letan: {}, locker: {}, tapvu: {} }
      setShiftDefinitions(definitions)
      setShiftDrafts(department === 'quanly' ? [] : Object.entries(definitions?.[department] || {}).map(([shift_code, spec]) => ({
        shift_code,
        start_time: spec?.start || '',
        end_time: spec?.end || '',
      })))
      setSaved(mapped)
      setDrafts(mapped)
      importedAwaitingManualSaveRef.current = false
      autoSaveAttemptRef.current = ''
      setAutoSaveState('saved')

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

  useEffect(() => { void load() }, [department, month, rangeKey]) // eslint-disable-line react-hooks/exhaustive-deps

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
    autoSaveAttemptRef.current = ''
    setAutoSaveState('pending')
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
      if (department !== 'quanly') {
        next.start_time = ''
        next.end_time = ''
      }
      if (field === 'overtime_shift' && value !== 'Từ giờ tới giờ') {
        next.overtime_start_time = ''
        next.overtime_end_time = ''
      }
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
    autoSaveAttemptRef.current = ''
    setAutoSaveState('pending')
    setSelectedCell({ username, day })
    setPastePanelOpen(false)
    setNotice(`Đã áp dụng lịch vào ngày ${day}; hệ thống sẽ tự lưu.`)
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
    autoSaveAttemptRef.current = ''
    setAutoSaveState('pending')
    setPastePanelOpen(false)
    setNotice(`Đã áp dụng lịch cho ${targetDays.length} ngày; hệ thống sẽ tự lưu.`)
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

  const pendingChanges = useMemo(() => {
    const output = []
    for (const employee of employees) {
      for (const date of days) {
        const day = isoDate(date)
        const key = keyFor(employee.username, day)
        const before = { ...emptyCell(), ...(saved[key] || {}) }
        const after = { ...emptyCell(), ...(drafts[key] || {}) }
        if (JSON.stringify(before) !== JSON.stringify(after)) output.push({ employee, day, key, before, after })
      }
    }
    return output
  }, [days, drafts, employees, saved])

  const pendingSignature = useMemo(
    () => JSON.stringify(pendingChanges.map(({ key, after }) => [key, after])),
    [pendingChanges],
  )

  const saveChanges = async (automatic = false) => {
    if (!canEdit) return
    if (!pendingChanges.length) {
      if (!automatic) setNotice('Mọi thay đổi lịch đã được lưu.')
      setAutoSaveState('saved')
      if (!automatic) importedAwaitingManualSaveRef.current = false
      return
    }
    setBusy(true)
    setAutoSaveState('saving')
    if (!automatic) setNotice('')
    try {
      const rows = []
      const deletes = []
      for (const { employee, day, before, after } of pendingChanges) {
        if (!after.shift_code) {
          if (before.shift_code) deletes.push({ day, username: employee.username })
          continue
        }
        if (department === 'quanly' && after.shift_code === 'Giờ làm' && (!after.start_time || !after.end_time)) {
          throw new Error(`${systemName(employee)} · ${day}: cần đủ giờ bắt đầu và giờ kết thúc.`)
        }
        if (overtimeMode(after) === 'Từ giờ tới giờ' && (!after.overtime_start_time || !after.overtime_end_time)) {
          throw new Error(`${systemName(employee)} · ${day}: tăng ca cần đủ giờ bắt đầu và giờ kết thúc.`)
        }
        rows.push({
          work_date: day,
          employee_username: employee.username,
          employee_name: systemName(employee),
          department,
          shift_code: after.shift_code,
          overtime_shift: overtimeMode(after),
          start_time: department === 'quanly' ? (after.start_time || '') : '',
          end_time: department === 'quanly' ? (after.end_time || '') : '',
          overtime_start_time: overtimeMode(after) === 'Từ giờ tới giờ' ? (after.overtime_start_time || '') : '',
          overtime_end_time: overtimeMode(after) === 'Từ giờ tới giờ' ? (after.overtime_end_time || '') : '',
          note: after.note || '',
          combo_sold: ['quanly', 'letan'].includes(department) && Boolean(after.combo_sold),
          combo_sale_date: after.combo_sold ? (after.combo_sale_date || day) : null,
          combo_customer_name: after.combo_sold ? (after.combo_customer_name || '') : '',
          combo_customer_phone: after.combo_sold ? (after.combo_customer_phone || '') : '',
          combo_ticket: after.combo_sold ? (after.combo_ticket || '') : '',
          combo_note: after.combo_sold ? (after.combo_note || '') : '',
        })
      }
      if (rows.length) await scheduleRequest('/v2/work-schedule', { method: 'PUT', body: JSON.stringify({ rows }) })
      for (const item of deletes) {
        await scheduleRequest(`/v2/work-schedule?work_date=${item.day}&employee_username=${encodeURIComponent(item.username)}`, { method: 'DELETE' })
      }
      setSaved((current) => {
        const next = { ...current }
        pendingChanges.forEach(({ key, after }) => {
          if (after.shift_code) next[key] = { ...emptyCell(), ...after }
          else delete next[key]
        })
        return next
      })
      setMonthlyRows((current) => {
        const changedKeys = new Set(pendingChanges.map(({ employee, day }) => keyFor(employee.username, day)))
        const retained = current.filter((row) => !changedKeys.has(keyFor(row.employee_username, row.work_date)))
        const monthBounds = monthRange(month)
        return [...retained, ...rows.filter((row) => row.work_date >= monthBounds.start && row.work_date <= monthBounds.end)]
      })
      setAutoSaveState('saved')
      if (!automatic) importedAwaitingManualSaveRef.current = false
      setNotice(automatic
        ? `Đã tự lưu ${rows.length + deletes.length} thay đổi lịch làm việc.`
        : `Đã lưu ${rows.length + deletes.length} thay đổi lịch làm việc.`)
    } catch (error) {
      setAutoSaveState('error')
      setNotice(error.message || 'Không lưu được lịch làm việc.')
    } finally {
      setBusy(false)
    }
  }

  useEffect(() => {
    if (!canEdit || loading || busy || importedAwaitingManualSaveRef.current || !pendingChanges.length || autoSaveAttemptRef.current === pendingSignature) return undefined
    setAutoSaveState('pending')
    window.clearTimeout(autoSaveTimerRef.current)
    autoSaveTimerRef.current = window.setTimeout(() => {
      autoSaveAttemptRef.current = pendingSignature
      void saveChanges(true)
    }, 900)
    return () => window.clearTimeout(autoSaveTimerRef.current)
  }, [busy, canEdit, loading, pendingSignature]) // eslint-disable-line react-hooks/exhaustive-deps

  const exportScheduleTemplate = async () => {
    setBusy(true)
    setNotice('')
    try {
      const path = `/v2/work-schedule/template.xlsx?${new URLSearchParams({ start: rangeStart, end: rangeEnd, department })}`
      const blob = await scheduleFileRequest(path, { download: true })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `Lich_lam_viec_${department}_${rangeStart}_${rangeEnd}.xlsx`
      anchor.click()
      window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      setNotice('Đã xuất file mẫu Excel kèm đầy đủ danh sách chọn Nhân viên, Ca làm, Tăng ca và Bộ phận.')
    } catch (error) {
      setNotice(error.message || 'Không xuất được file mẫu lịch làm việc.')
    } finally {
      setBusy(false)
    }
  }

  const importScheduleTemplate = async (file) => {
    if (!file || !canEdit) return
    setBusy(true)
    setNotice('')
    try {
      const path = `/v2/work-schedule/import.xlsx?${new URLSearchParams({ start: rangeStart, end: rangeEnd, department })}`
      const result = await scheduleFileRequest(path, {
        method: 'POST',
        body: file,
        headers: { 'Content-Type': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' },
      })
      const imported = Object.fromEntries((result.rows || []).map((row) => [keyFor(row.employee_username, row.work_date), {
        ...emptyCell(),
        shift_code: row.shift_code || '',
        overtime_shift: row.overtime_shift || '',
        start_time: row.start_time || '',
        end_time: row.end_time || '',
        overtime_start_time: row.overtime_start_time || '',
        overtime_end_time: row.overtime_end_time || '',
        note: row.note || '',
      }]))
      setDrafts((current) => ({ ...current, ...imported }))
      importedAwaitingManualSaveRef.current = true
      autoSaveAttemptRef.current = ''
      setAutoSaveState('pending')
      setNotice(result.message || 'Đã nạp Excel. Kiểm tra và bấm Lưu lịch để ghi vào hệ thống.')
    } catch (error) {
      setNotice(error.message || 'Không Import được file lịch làm việc.')
    } finally {
      setBusy(false)
      if (scheduleFileInputRef.current) scheduleFileInputRef.current.value = ''
    }
  }

  useEffect(() => {
    if (!pendingChanges.length && autoSaveState !== 'saving') setAutoSaveState('saved')
  }, [autoSaveState, pendingChanges.length])

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
        const overtimeTarget = String(value.overtime_shift || '').replace(/^TC\s+/i, '')
        if (['Ca 1', 'Ca 2'].includes(overtimeTarget) && counts[overtimeTarget]) {
          counts[overtimeTarget].overtime += 1
        } else if (overtimeMode(value) === 'Từ giờ tới giờ') {
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

  const monthlyStatistics = useMemo(() => {
    const definitions = shiftDefinitions?.[department] || {}
    const byEmployee = Object.fromEntries(employees.map((employee) => [employee.username, {
      username: employee.username, name: systemName(employee), workDays: 0, offDays: 0, ca1Days: 0, ca2Days: 0, overtimeHours: 0,
    }]))
    monthlyRows.filter((row) => row.work_date <= yesterdayIso).forEach((row) => {
      const item = byEmployee[row.employee_username]
      if (!item || !row.shift_code) return
      if (row.shift_code === 'Nghỉ') {
        item.offDays += 1
        return
      }
      item.workDays += 1
      const bucket = workShiftBucket(row)
      if (bucket === 'Ca 1') item.ca1Days += 1
      if (bucket === 'Ca 2') item.ca2Days += 1
      item.overtimeHours += overtimeHours(row, definitions)
    })
    const rows = Object.values(byEmployee)
    const departmentTotal = rows.reduce((total, item) => ({
      workDays: total.workDays + item.workDays,
      offDays: total.offDays + item.offDays,
      ca1Days: total.ca1Days + item.ca1Days,
      ca2Days: total.ca2Days + item.ca2Days,
      overtimeHours: total.overtimeHours + item.overtimeHours,
    }), { workDays: 0, offDays: 0, ca1Days: 0, ca2Days: 0, overtimeHours: 0 })
    return { rows, departmentTotal }
  }, [department, employees, monthlyRows, shiftDefinitions, yesterdayIso])

  const captureFullSchedule = async () => {
    if (loading || captureBusy) return
    setCaptureBusy(true)
    try {
      if (!navigator.clipboard?.write || !window.ClipboardItem) {
        throw new Error('Trình duyệt này chưa hỗ trợ chép ảnh vào bộ nhớ tạm. Hãy dùng Chrome hoặc Edge qua HTTPS.')
      }
      const nameWidth = 190
      const dayWidth = isMonthView ? 52 : 112
      const titleHeight = 52
      const headerHeight = 48
      const rowHeight = 38
      const summaryRows = department === 'quanly' ? [] : configuredShiftNames
      const logicalWidth = nameWidth + days.length * dayWidth
      const logicalHeight = titleHeight + headerHeight + (employees.length + summaryRows.length) * rowHeight
      const scale = Math.min(2, Math.max(1, window.devicePixelRatio || 1))
      const canvas = document.createElement('canvas')
      canvas.width = Math.ceil(logicalWidth * scale)
      canvas.height = Math.ceil(logicalHeight * scale)
      const context = canvas.getContext('2d')
      if (!context) throw new Error('Không khởi tạo được ảnh lịch làm việc.')
      context.scale(scale, scale)
      context.textBaseline = 'middle'

      const drawCell = (x, y, width, height, fill, text, options = {}) => {
        context.fillStyle = fill
        context.fillRect(x, y, width, height)
        context.strokeStyle = '#d8e3de'
        context.strokeRect(x, y, width, height)
        context.font = `${options.bold ? '700' : '500'} ${options.size || 11}px Arial, sans-serif`
        context.fillStyle = options.color || '#183d31'
        context.textAlign = options.align || 'center'
        const padding = 6
        const maxWidth = Math.max(4, width - padding * 2)
        let label = String(text || '')
        while (label.length > 1 && context.measureText(label).width > maxWidth) label = `${label.slice(0, -2)}…`
        const textX = options.align === 'left' ? x + padding : x + width / 2
        context.fillText(label, textX, y + height / 2)
      }

      context.fillStyle = '#173329'
      context.fillRect(0, 0, logicalWidth, titleHeight)
      context.fillStyle = '#fff'
      context.textAlign = 'left'
      context.font = '700 18px Arial, sans-serif'
      context.fillText(`VERA SPA · LỊCH LÀM VIỆC · ${DEPARTMENT_INFO[department].label.toUpperCase()}`, 12, 18)
      context.font = '500 11px Arial, sans-serif'
      context.fillText(rangeLabel, 12, 38)

      drawCell(0, titleHeight, nameWidth, headerHeight, '#dfeee8', 'Tên nhân viên', { bold: true, align: 'left', size: 12 })
      days.forEach((date, index) => {
        const fill = date.getDay() === 0 ? '#fff0ea' : '#eef6f3'
        drawCell(nameWidth + index * dayWidth, titleHeight, dayWidth, headerHeight, fill, `${WEEKDAYS_SHORT[date.getDay()]} ${displayDate(date)}`, { bold: true, size: isMonthView ? 8 : 10 })
      })

      employees.forEach((employee, rowIndex) => {
        const y = titleHeight + headerHeight + rowIndex * rowHeight
        drawCell(0, y, nameWidth, rowHeight, '#fff', systemName(employee), { bold: true, align: 'left', size: 11 })
        days.forEach((date, dayIndex) => {
          const day = isoDate(date)
          const value = { ...emptyCell(), ...(drafts[keyFor(employee.username, day)] || {}) }
          const fill = value.shift_code === 'Ca 1' ? '#dff3cc'
            : value.shift_code === 'Ca 2' ? '#fff8a8'
              : value.shift_code === 'Nghỉ' ? '#ffe0b8'
                : date.getDay() === 0 ? '#fff6f2' : '#fff'
          drawCell(nameWidth + dayIndex * dayWidth, y, dayWidth, rowHeight, fill, compactCellLabel(value, department), { bold: true, size: isMonthView ? 8 : 10 })
        })
      })

      summaryRows.forEach((shift, summaryIndex) => {
        const y = titleHeight + headerHeight + (employees.length + summaryIndex) * rowHeight
        drawCell(0, y, nameWidth, rowHeight, '#e7f1ed', `Tổng NV · ${shift}`, { bold: true, align: 'left', size: 10 })
        days.forEach((date, dayIndex) => {
          const day = isoDate(date)
          const counts = shiftSummary?.[day]?.[shift] || { regular: 0, overtime: 0, total: 0 }
          drawCell(nameWidth + dayIndex * dayWidth, y, dayWidth, rowHeight, '#f4f8f6', `${counts.total} (${counts.regular}+${counts.overtime})`, { bold: true, size: isMonthView ? 7 : 9 })
        })
      })

      const blob = await canvasToPngBlob(canvas)
      await navigator.clipboard.write([new window.ClipboardItem({ 'image/png': blob })])
      setNotice(`Đã chụp toàn bộ bảng ${rangeLabel} và lưu ảnh PNG vào bộ nhớ tạm. Bạn có thể nhấn Ctrl+V để dán.`)
    } catch (error) {
      setNotice(error.message || 'Không chụp được toàn bộ bảng lịch làm việc.')
    } finally {
      setCaptureBusy(false)
    }
  }

  const employeeMatchesTotal = (employee, day, shift) => {
    const value = { ...emptyCell(), ...(drafts[keyFor(employee.username, day)] || {}) }
    if (value.shift_code === shift || value.overtime_shift === `TC ${shift}`) return true
    const spec = shiftDefinitions?.[department]?.[shift] || {}
    return overtimeMode(value) === 'Từ giờ tới giờ'
      && timeRangesOverlap(spec.start, spec.end, value.overtime_start_time, value.overtime_end_time)
  }

  const editorFor = (employee, day, value) => {
    const shiftClass = value.shift_code === 'Ca 1' ? 'ca1' : value.shift_code === 'Ca 2' ? 'ca2' : value.shift_code === 'Nghỉ' ? 'off' : ''
    const shiftNames = value.shift_code && !['Nghỉ', 'Giờ làm'].includes(value.shift_code) && !configuredShiftNames.includes(value.shift_code)
      ? [value.shift_code, ...configuredShiftNames] : configuredShiftNames
    const currentOvertimeMode = overtimeMode(value)
    const overtimeEditor = <div className="shared-overtime">
      <select className={`ot-select ${currentOvertimeMode ? 'active' : 'no-overtime'}`} value={currentOvertimeMode} disabled={!canEdit || !value.shift_code || value.shift_code === 'Nghỉ'} onChange={(event) => setCell(employee.username, day, 'overtime_shift', event.target.value)}>
        <option value="">Không TC</option><option>TC Ca 1</option><option>TC Ca 2</option><option>Từ giờ tới giờ</option>
      </select>
      {currentOvertimeMode === 'Từ giờ tới giờ' && <div className="overtime-time-row">
        <input className="letan-ot-time" aria-label="Tăng ca từ giờ" type="time" value={value.overtime_start_time || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'overtime_start_time', event.target.value)} />
        <span>–</span>
        <input className="letan-ot-time" aria-label="Tăng ca tới giờ" type="time" value={value.overtime_end_time || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'overtime_end_time', event.target.value)} />
      </div>}
    </div>

    if (department === 'quanly') {
      return <div className="manager-cell">
        <select className={`manager-status ${value.shift_code === 'Nghỉ' ? 'off' : ''}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
          <option value="">—</option><option value="Giờ làm">Làm việc</option><option value="Nghỉ">Nghỉ</option>
        </select>
        {value.shift_code === 'Giờ làm' && <div className="manager-time-row">
          <input className="manager-time" type="time" value={value.start_time || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'start_time', event.target.value)} />
          <input className="manager-time" type="time" value={value.end_time || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'end_time', event.target.value)} />
        </div>}
        {overtimeEditor}
      </div>
    }

    return <div className="schedule-cell">
      <select className={`shift-select ${shiftClass}`} value={value.shift_code || ''} disabled={!canEdit} onChange={(event) => setCell(employee.username, day, 'shift_code', event.target.value)}>
        <option value="">—</option>
        {shiftNames.map((shift) => <option key={shift} value={shift}>{shift}{!configuredShiftNames.includes(shift) ? ' (cũ)' : ''}</option>)}
        <option value="Nghỉ">Nghỉ</option>
      </select>
      {overtimeEditor}
    </div>
  }

  const selectedEmployee = employees.find((item) => item.username === selectedCell?.username)
  const selectedValue = selectedCell ? { ...emptyCell(), ...(drafts[keyFor(selectedCell.username, selectedCell.day)] || {}) } : null

  const comboEmployees = useMemo(() => {
    const mapped = new Map(employees.map((employee) => [String(employee.username || '').toLowerCase(), employee]))
    comboSales.forEach((sale) => {
      const key = String(sale.employee_username || '').toLowerCase()
      if (key && !mapped.has(key)) mapped.set(key, { username: sale.employee_username, full_name: sale.employee_name })
    })
    return [...mapped.values()]
  }, [comboSales, employees])

  const saveComboSale = async (employee, draft, saleId = '') => {
    if (!employee || !draft.sale_date || !draft.customer_name.trim() || !draft.combo_ticket.trim()) {
      setNotice('Bán combo cần đủ Ngày bán, Tên khách hàng và Vé combo.')
      return false
    }
    setBusy(true)
    try {
      const path = saleId ? `/v2/work-schedule/combo-sales/${encodeURIComponent(saleId)}` : '/v2/work-schedule/combo-sales'
      const result = await scheduleRequest(path, {
        method: saleId ? 'PUT' : 'POST',
        body: JSON.stringify({
          ...draft,
          employee_username: employee.username,
          employee_name: systemName(employee),
          department,
        }),
      })
      await load()
      setNotice(result.message || (saleId ? 'Đã cập nhật lượt bán combo.' : 'Đã thêm lượt bán combo.'))
      return true
    } catch (error) {
      setNotice(error.message || 'Không lưu được dữ liệu bán combo.')
      return false
    } finally { setBusy(false) }
  }

  const deleteComboSale = async (sale) => {
    if (!window.confirm(`Xóa lượt bán combo của ${sale.employee_name} ngày ${sale.sale_date}?`)) return
    setBusy(true)
    try { await scheduleRequest(`/v2/work-schedule/combo-sales/${encodeURIComponent(sale.id)}`, { method: 'DELETE' }); await load(); setNotice('Đã xóa lượt bán combo.') }
    catch (error) { setNotice(error.message || 'Không xóa được dữ liệu bán combo.') } finally { setBusy(false) }
  }

  const exportComboSales = async () => {
    const statisticsRange = monthRange(month)
    setBusy(true)
    try {
      await veraApi.exportComboSalesExcel(statisticsRange.start, statisticsRange.end, department)
      setNotice('Đã Export Excel bán combo theo từng nhân viên.')
    } catch (error) { setNotice(error.message || 'Không Export được Excel bán combo.') } finally { setBusy(false) }
  }

  const importComboSales = async (event) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    if (!file.name.toLowerCase().endsWith('.xlsx')) return setNotice('Vui lòng chọn file Excel .xlsx.')
    setBusy(true)
    try {
      const result = await veraApi.importComboSalesExcel(file, department)
      await load()
      setNotice(result.message || 'Đã Import Excel bán combo.')
    } catch (error) { setNotice(error.message || 'Không Import được Excel bán combo.') } finally { setBusy(false) }
  }

  const comboEditor = ['quanly', 'letan'].includes(department)
    ? <div className="combo-sale-editor">
      <div className="combo-sale-head"><strong>BẢNG BÁN COMBO · {DEPARTMENT_INFO[department].label}</strong>{canEditCombo && <div className="combo-excel-actions"><input ref={comboFileInputRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(event) => void importComboSales(event)} /><button type="button" className="schedule-copy-button" disabled={busy} onClick={() => comboFileInputRef.current?.click()}><Upload size={15}/> Import Excel</button><button type="button" className="schedule-copy-button" disabled={busy} onClick={() => void exportComboSales()}><Download size={15}/> Export Excel</button></div>}</div>
      <div className="combo-employee-sections">{comboEmployees.map((employee) => {
        const employeeRows = comboSales.filter((sale) => String(sale.employee_username || '').toLowerCase() === String(employee.username || '').toLowerCase())
        return <ComboEmployeeTable key={`${department}-${month}-${employee.username}`} employee={employee} rows={employeeRows} defaultDate={comboDefaultDate} canEdit={canEditCombo} busy={busy} onSave={saveComboSale} onDelete={deleteComboSale} />
      })}</div>
      {!comboEmployees.length && <div className="revenue-meta">Chưa có nhân viên {DEPARTMENT_INFO[department].label} để tạo bảng bán combo.</div>}
    </div> : null

  if (!availableDepartments.length) return <section className="work-schedule-page"><div className="warning-box">Tài khoản chưa được cấp quyền Lịch làm việc.</div></section>

  return <section className="work-schedule-page">
    <style>{`
      .work-schedule-page{display:grid;gap:14px}.schedule-head{display:flex;gap:12px;align-items:flex-start;justify-content:space-between;flex-wrap:wrap}.schedule-title h2{margin:0}.schedule-range{margin-top:7px;font-size:13px;font-weight:800;color:#1f513f}.schedule-tools{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.schedule-month-picker{display:flex;align-items:center;gap:6px;border:1px solid #d7e2dd;border-radius:12px;padding:5px 7px;background:#fff}.schedule-month-picker input{border:0;background:transparent;font:inherit;font-weight:800;color:#25483b;min-width:142px}.schedule-icon-button{border:0;background:#eef5f2;color:#244a3a;border-radius:8px;width:34px;height:34px;display:grid;place-items:center}.schedule-filter-bar{display:flex;gap:6px;flex-wrap:wrap}.schedule-filter-bar button{border:1px solid #d6e2dd;background:#fff;border-radius:999px;padding:7px 11px;font-weight:800;color:#466057}.schedule-filter-bar button.active{background:#173329;border-color:#173329;color:#fff}.schedule-custom-range{display:inline-flex;gap:7px;align-items:center;width:max-content;max-width:100%}.schedule-custom-range input{border:1px solid #d6e2dd;border-radius:9px;padding:7px;width:170px;min-width:0}.schedule-department-tabs{display:flex;gap:6px;flex-wrap:wrap}.schedule-department-tabs button{border:1px solid #d7e2dd;background:#fff;border-radius:10px;padding:8px 11px;font-weight:800;color:#4a5d55}.schedule-department-tabs button.active{background:#173329;color:#fff;border-color:#173329}.schedule-legend{display:flex;gap:12px;flex-wrap:wrap;padding:10px 12px;border:1px solid #dfe8e5;border-radius:12px;background:#f8fbfa;font-size:13px}.schedule-scroll{overflow-x:auto;border:1px solid #dfe8e5;border-radius:14px;background:#fff;max-width:100%}.schedule-grid{border-collapse:separate;border-spacing:0;min-width:max-content;width:100%}.schedule-grid th,.schedule-grid td{border-right:1px solid #e6ecea;border-bottom:1px solid #e6ecea;padding:6px;text-align:center;vertical-align:middle}.schedule-grid thead th{position:sticky;top:0;background:#eef6f3;z-index:4;min-width:116px}.schedule-grid thead tr:nth-child(2) th{top:35px}.schedule-grid thead th.employee-head{left:0;z-index:8;min-width:170px}.schedule-grid td.employee-cell,.schedule-grid tfoot td.summary-label{position:sticky;left:0;background:#fff;z-index:3;text-align:left;min-width:170px}.schedule-grid .month-head{height:35px;background:#dfeee8;font-weight:900;color:#244a3a}.schedule-grid .sunday{background:#fff6f2}.schedule-grid .today{box-shadow:inset 0 0 0 2px #bb8b34}.schedule-grid td.selected{box-shadow:inset 0 0 0 3px #245b47;background:#eff8f4}.schedule-grid tr.own-row td.employee-cell{background:#eef8f3}.schedule-grid tr.own-row td.employee-cell strong:after{content:' · Lịch của bạn';font-size:11px;color:#267051}.employee-name-line{display:flex;gap:5px;align-items:center}.employee-highlight-button{border:0;background:transparent;color:inherit;padding:4px 5px;margin:-4px -5px;border-radius:7px;text-align:left;cursor:pointer}.employee-highlight-button.active{background:#1f6b4d;color:#fff}.schedule-grid th.employee-work-day{background:#ccebdc;color:#155b3e;box-shadow:inset 0 -3px 0 #1f7a54}.schedule-grid td.employee-work-day{background:#e2f6eb!important;outline:3px solid #2b8a61;outline-offset:-3px}.system-name-edit{border:0;background:transparent;color:#5b7168;padding:2px;display:grid;place-items:center}.employee-role{display:block;color:#708079;font-size:11px;margin-top:2px}.schedule-cell{display:grid;gap:5px}.shift-select,.ot-select,.manager-status,.manager-time,.letan-ot-time{border:1px solid #d9e2df;border-radius:8px;background:#fff}.shift-select,.ot-select{width:108px;padding:5px;font-size:12px}.shift-select.ca1{background:#dff3cc}.shift-select.ca2{background:#fff8a8}.shift-select.off,.manager-status.off{background:#ffe0b8}.ot-select.no-overtime{color:#d5dfdb;border-color:#edf2f0;background:#fbfcfc}.ot-select.active{color:#244a3a}.manager-cell{display:grid;gap:5px;min-width:136px}.manager-status{width:126px;padding:5px;font-size:12px}.manager-time-row{display:grid;grid-template-columns:1fr 1fr;gap:4px}.manager-time{width:61px;padding:5px 3px;font-size:11px}.shared-overtime{display:grid;gap:4px}.overtime-time-row{display:grid;grid-template-columns:1fr auto 1fr;align-items:center;gap:2px}.letan-ot-time{width:48px;padding:4px 1px;font-size:10px}.schedule-save,.schedule-copy-button,.schedule-config-button{display:inline-flex;align-items:center;gap:7px;border:0;border-radius:10px;padding:9px 13px;font-weight:700}.schedule-save{background:#173329;color:white}.schedule-copy-button,.schedule-config-button{background:#eef5f2;color:#214538;border:1px solid #ccddd5}.schedule-save:disabled,.schedule-copy-button:disabled,.schedule-config-button:disabled{opacity:.5}.schedule-notice{padding:10px 12px;border-radius:10px;background:#edf7f3}.schedule-autosave-state{display:inline-flex;align-items:center;min-height:34px;padding:0 10px;border-radius:999px;background:#edf7f3;color:#256047;font-size:12px;font-weight:900}.schedule-autosave-state.pending{background:#fff6d6;color:#7a5a00}.schedule-autosave-state.saving{background:#e8f0ff;color:#28549d}.schedule-autosave-state.error{background:#fff0f0;color:#a43131}.paste-range-panel,.shift-editor{display:grid;gap:10px;padding:12px;border:1px solid #d8e5df;border-radius:12px;background:#fbfdfc}.paste-range-panel{grid-template-columns:auto auto auto auto;align-items:end}.paste-range-panel label,.shift-editor label{display:grid;gap:4px;font-size:12px;font-weight:800}.paste-range-panel input,.shift-editor input{border:1px solid #d5e0dc;border-radius:8px;padding:8px;background:#fff}.shift-editor-rows{display:grid;gap:8px}.shift-editor-row{display:grid;grid-template-columns:minmax(140px,1fr) 110px 110px 42px;gap:8px;align-items:end}.shift-editor-row button{height:36px;border:1px solid #efd3d3;background:#fff4f4;color:#9b3636;border-radius:8px}.shift-editor-actions,.shift-editor-head{display:flex;gap:8px;justify-content:space-between;align-items:center;flex-wrap:wrap}.schedule-grid tfoot td{background:#f4f8f6;font-size:11px;font-weight:700}.schedule-grid tfoot td.summary-label{background:#e7f1ed;font-weight:900}.shift-total-cell{display:grid;gap:2px;min-width:100px;width:100%;border:0;background:transparent;border-radius:8px;padding:4px;cursor:pointer}.shift-total-cell.active{background:#1f6b4d}.shift-total-cell b{font-size:15px;color:#173329}.shift-total-cell small{color:#6a7a73}.shift-total-cell.active b,.shift-total-cell.active small{color:#fff}.monthly-statistics{display:grid;gap:8px}.monthly-statistics h3{margin:0;color:#173329}.monthly-statistics table{width:100%;border-collapse:collapse;background:#fff}.monthly-statistics th,.monthly-statistics td{border:1px solid #dfe8e5;padding:8px;text-align:center}.monthly-statistics th:first-child,.monthly-statistics td:first-child{text-align:left}.monthly-statistics tfoot td{background:#e7f1ed;font-weight:900}.weekday-short,.mobile-cell-summary,.mobile-week-editor{display:none}.schedule-scroll.month-view{overflow-x:hidden}.schedule-scroll.month-view .schedule-grid{width:100%;min-width:0;table-layout:fixed}.schedule-scroll.month-view .schedule-grid thead th{min-width:0;padding:3px 1px;font-size:8px}.schedule-scroll.month-view .schedule-grid thead th.employee-head,.schedule-scroll.month-view .schedule-grid td.employee-cell,.schedule-scroll.month-view .schedule-grid tfoot td.summary-label{width:116px;min-width:116px;max-width:116px;padding:4px;white-space:normal;overflow:hidden}.schedule-scroll.month-view .schedule-grid td{min-width:0;padding:2px 1px}.schedule-scroll.month-view .weekday-full{display:none}.schedule-scroll.month-view .weekday-short{display:block;font-size:7px}.schedule-scroll.month-view .schedule-cell-editor{display:none}.schedule-scroll.month-view .mobile-cell-summary{display:block;overflow:hidden;padding:5px 0;border-radius:4px;font-size:7px;font-weight:900;line-height:1;color:#244a3a;white-space:nowrap;text-overflow:ellipsis}.schedule-scroll.month-view .mobile-cell-summary.ca1{background:#dff3cc}.schedule-scroll.month-view .mobile-cell-summary.ca2{background:#fff8a8}.schedule-scroll.month-view .mobile-cell-summary.off{background:#ffe0b8}.schedule-scroll.month-view .employee-cell strong{font-size:9px;line-height:1.1}.schedule-scroll.month-view .employee-role,.schedule-scroll.month-view tr.own-row td.employee-cell strong:after,.schedule-scroll.month-view .system-name-edit{display:none}.schedule-scroll.month-view .month-head{height:28px;font-size:10px}.schedule-scroll.month-view .schedule-grid thead tr:nth-child(2) th{top:28px}.schedule-scroll.month-view .shift-total-cell{min-width:0;padding:2px}.schedule-scroll.month-view .shift-total-cell b{font-size:10px}.schedule-scroll.month-view .shift-total-cell small{display:none}.mobile-week-editor.month-editor{display:grid;gap:8px;padding:10px;border:1px solid #d5e3dd;border-radius:12px;background:#f8fbfa}
      @media(max-width:700px){.schedule-tools{width:100%}.schedule-copy-button,.schedule-save,.schedule-config-button{flex:1;justify-content:center}.schedule-month-picker{width:100%;justify-content:space-between}.schedule-filter-bar{display:grid;grid-template-columns:repeat(3,1fr);gap:4px}.schedule-filter-bar button{padding:7px 2px;font-size:10px}.schedule-custom-range{display:grid;grid-template-columns:1fr 1fr;width:100%;max-width:100%}.schedule-custom-range input{min-width:0;width:100%}.paste-range-panel{grid-template-columns:1fr 1fr}.shift-editor-row{grid-template-columns:1fr 1fr}.shift-editor-row label:first-child{grid-column:1/-1}.schedule-scroll.week-view{overflow-x:hidden}.schedule-scroll.week-view .schedule-grid{min-width:0;width:100%;table-layout:fixed}.schedule-scroll.week-view .schedule-grid thead th{min-width:0;padding:3px 1px;font-size:9px}.schedule-scroll.week-view .weekday-full{display:none}.schedule-scroll.week-view .weekday-short{display:block}.schedule-scroll.week-view .schedule-grid thead th.employee-head,.schedule-scroll.week-view .schedule-grid td.employee-cell,.schedule-scroll.week-view .schedule-grid tfoot td.summary-label{width:72px;min-width:72px;max-width:72px;padding:3px;white-space:normal;word-break:break-word}.schedule-scroll.week-view .schedule-grid td{padding:2px 1px;min-width:0}.schedule-scroll.week-view .employee-cell strong{font-size:9px;line-height:1.1}.schedule-scroll.week-view .employee-role,.schedule-scroll.week-view tr.own-row td.employee-cell strong:after,.schedule-scroll.week-view .system-name-edit{display:none}.schedule-scroll.week-view .schedule-cell-editor{display:none}.schedule-scroll.week-view .mobile-cell-summary{display:block;padding:5px 1px;border-radius:6px;font-size:9px;font-weight:900;line-height:1.1;color:#244a3a}.schedule-scroll.week-view .mobile-cell-summary.ca1{background:#dff3cc}.schedule-scroll.week-view .mobile-cell-summary.ca2{background:#fff8a8}.schedule-scroll.week-view .mobile-cell-summary.off{background:#ffe0b8}.schedule-scroll.week-view .month-head{font-size:10px;height:28px}.schedule-scroll.week-view .schedule-grid thead tr:nth-child(2) th{top:28px}.schedule-scroll.week-view .shift-total-cell{min-width:0;font-size:8px}.schedule-scroll.week-view .shift-total-cell b{font-size:11px}.schedule-scroll.week-view .shift-total-cell small{font-size:7px}.mobile-week-editor{display:grid;gap:8px;padding:10px;border:1px solid #d5e3dd;border-radius:12px;background:#f8fbfa}.mobile-week-editor .shift-select,.mobile-week-editor .ot-select,.mobile-week-editor .manager-status,.mobile-week-editor .manager-time,.mobile-week-editor .letan-ot-time{width:100%}}
    `}</style>
    <style>{`
      .combo-sale-editor{display:grid;gap:10px;padding:12px;border:1px solid #d8e5df;border-radius:12px;background:#f8fbfa}
      .combo-sale-head{display:flex;align-items:center;justify-content:space-between;gap:12px;flex-wrap:wrap}
      .combo-sale-head label{display:flex;align-items:center;gap:7px;font-weight:800;color:#1f6047}
      .combo-excel-actions,.combo-form-actions,.combo-row-actions{display:flex;align-items:center;gap:7px;flex-wrap:wrap}
      .combo-employee-sections{display:grid;gap:14px}
      .combo-employee-card{display:grid;gap:10px;padding:12px;border:1px solid #ccddd5;border-radius:12px;background:#fff}
      .combo-employee-title{display:flex;justify-content:space-between;align-items:center;gap:10px;flex-wrap:wrap;color:#173329}
      .combo-employee-title span{font-size:12px;color:#66776f;font-weight:700}
      .combo-sale-fields{display:grid;grid-template-columns:repeat(4,minmax(140px,1fr));gap:9px}
      .combo-sale-fields label{display:grid;gap:4px;font-size:12px;font-weight:800;color:#365348}
      .combo-sale-fields input,.combo-sale-fields select,.combo-sale-fields textarea{border:1px solid #d5e0dc;border-radius:8px;padding:8px;background:#fff;font:inherit}
      .combo-form-actions{align-self:end}
      .combo-sale-table{width:100%;border-collapse:collapse;min-width:700px}.combo-sale-table th,.combo-sale-table td{border:1px solid #dfe8e5;padding:8px;text-align:left}.combo-sale-table th{background:#e7f1ed}.combo-edit,.combo-delete{border:0;border-radius:7px;padding:6px}.combo-edit{color:#1f6047;background:#eaf5f0}.combo-delete{color:#a33;background:#fff0f0}
      @media(max-width:700px){.combo-sale-fields{grid-template-columns:1fr}.combo-excel-actions{width:100%}.combo-excel-actions button{flex:1;justify-content:center}}
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
        <button type="button" className="schedule-copy-button" onClick={() => void exportScheduleTemplate()} disabled={busy || loading}><Download size={16}/> Xuất Excel mẫu</button>
        {canEdit && <><button type="button" className="schedule-copy-button" onClick={() => scheduleFileInputRef.current?.click()} disabled={busy || loading}><Upload size={16}/> Import Excel</button><input ref={scheduleFileInputRef} type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" hidden onChange={(event) => void importScheduleTemplate(event.target.files?.[0])} /></>}
        <button type="button" className="schedule-copy-button" onClick={() => void captureFullSchedule()} disabled={loading || captureBusy}>{captureBusy ? <LoaderCircle size={16} className="spin" /> : <Camera size={16}/>} {captureBusy ? 'Đang chụp…' : 'Chụp toàn bộ bảng'}</button>
        {canEdit && department !== 'quanly' && <button type="button" className="schedule-config-button" onClick={() => setShiftEditorOpen((value) => !value)}><Settings2 size={16}/> Tạo / sửa ca</button>}
        {canEdit && <button type="button" className="schedule-save" onClick={() => void saveChanges(false)} disabled={busy || loading || !pendingChanges.length}>{busy ? <LoaderCircle size={16} className="spin" /> : <Save size={16}/>} Lưu lịch</button>}
        {canEdit && <span className={`schedule-autosave-state ${autoSaveState}`}>{importedAwaitingManualSaveRef.current ? 'Excel chờ Lưu lịch' : autoSaveState === 'saving' ? 'Đang tự lưu…' : autoSaveState === 'pending' ? 'Chờ tự lưu' : autoSaveState === 'error' ? 'Tự lưu lỗi' : 'Đã tự lưu'}</span>}
      </div>
    </div>

    <div className="schedule-filter-bar">{RANGE_FILTERS.map(([mode, label]) => <button type="button" key={mode} className={rangeMode === mode ? 'active' : ''} onClick={() => selectRange(mode)}>{label}</button>)}</div>
    {rangeMode === 'custom' && <div className="schedule-custom-range">
      <VeraDateInput aria-label="Từ ngày" value={customStart} onChange={(event) => { const value = event.target.value; setCustomStart(value); if (customEnd < value) setCustomEnd(value) }} />
      <VeraDateInput aria-label="Đến ngày" min={customStart} value={customEnd} onChange={(event) => setCustomEnd(event.target.value)} />
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
      <label>Từ ngày<VeraDateInput aria-label="Từ ngày" value={selectedCell.day} readOnly /></label>
      <label>Đến ngày<VeraDateInput aria-label="Đến ngày" min={selectedCell.day} max={rangeEnd} value={pasteEndDay} onChange={(event) => setPasteEndDay(event.target.value)} /></label>
      <button type="button" className="schedule-save" onClick={applyPasteRange}><ClipboardPaste size={15}/> Áp dụng</button>
    </div>}
    {notice && <div className="schedule-notice">{notice}</div>}

    {(isWeekView || isMonthView) && selectedCell && selectedEmployee && selectedValue && canEdit && <div className={`mobile-week-editor ${isMonthView ? 'month-editor' : ''}`}><strong>{systemName(selectedEmployee)} · {selectedCell.day}</strong>{editorFor(selectedEmployee, selectedCell.day, selectedValue)}</div>}

    {loading ? <div className="page-loading"><LoaderCircle size={18} className="spin" /> Đang tải lịch…</div> : <div className={`schedule-scroll ${isWeekView ? 'week-view' : ''} ${isMonthView ? 'month-view' : ''}`.trim()}>
      <table className="schedule-grid">
        <thead><tr><th className="employee-head" rowSpan="2">Tên nhân viên</th><th className="month-head" colSpan={days.length}>{rangeTitle}</th></tr><tr>{days.map((date) => {
          const day = isoDate(date)
          const classes = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : ''].filter(Boolean).join(' ')
          const highlightedValue = highlightedEmployee ? { ...emptyCell(), ...(drafts[keyFor(highlightedEmployee, day)] || {}) } : null
          const isEmployeeWorkDay = Boolean(highlightedValue?.shift_code && highlightedValue.shift_code !== 'Nghỉ')
          return <th key={day} className={[classes, isEmployeeWorkDay ? 'employee-work-day' : ''].filter(Boolean).join(' ')}><div className="weekday-full">{WEEKDAYS[date.getDay()]}</div><div className="weekday-short">{WEEKDAYS_SHORT[date.getDay()]}</div><small>{isMonthView ? date.getDate() : displayDate(date)}</small></th>
        })}</tr></thead>
        <tbody>{employees.map((employee) => {
          const isOwn = String(employee.username || '').toLowerCase() === ownUsername
          const isHighlightedEmployee = highlightedEmployee === employee.username
          const isHighlightedByTotal = Boolean(highlightedTotal && employeeMatchesTotal(employee, highlightedTotal.day, highlightedTotal.shift))
          return <tr key={employee.username} className={isOwn ? 'own-row' : ''}><td className="employee-cell"><div className="employee-name-line"><button type="button" className={`employee-highlight-button ${isHighlightedEmployee || isHighlightedByTotal ? 'active' : ''}`.trim()} aria-pressed={isHighlightedEmployee || isHighlightedByTotal} title="Highlight các ngày nhân viên làm việc" onClick={() => { setHighlightedTotal(null); setHighlightedEmployee((current) => current === employee.username ? '' : employee.username) }}><strong>{systemName(employee)}</strong></button>{isAdmin && <button type="button" className="system-name-edit" title="Đổi tên hệ thống" onClick={() => void renameSystemName(employee)}><PencilLine size={13}/></button>}</div><span className="employee-role">{DEPARTMENT_INFO[department].label}</span></td>{days.map((date) => {
            const day = isoDate(date)
            const value = { ...emptyCell(), ...(drafts[keyFor(employee.username, day)] || {}) }
            const isSelected = selectedCell?.username === employee.username && selectedCell?.day === day
            const isEmployeeWorkDay = isHighlightedEmployee && Boolean(value.shift_code && value.shift_code !== 'Nghỉ')
            const tdClass = [date.getDay() === 0 ? 'sunday' : '', day === todayIso ? 'today' : '', isSelected ? 'selected' : '', isEmployeeWorkDay ? 'employee-work-day' : ''].filter(Boolean).join(' ')
            const mobileShiftClass = value.shift_code === 'Ca 1' ? 'ca1' : value.shift_code === 'Ca 2' ? 'ca2' : value.shift_code === 'Nghỉ' ? 'off' : ''
            return <td key={day} className={tdClass} tabIndex={0} onFocus={() => setSelectedCell({ username: employee.username, day })} onClick={() => setSelectedCell({ username: employee.username, day })} onKeyDown={(event) => handleCellKeyDown(event, employee.username, day)}><div className="schedule-cell-editor">{editorFor(employee, day, value)}</div><div className={`mobile-cell-summary ${mobileShiftClass}`} title={compactCellLabel(value, department)}>{compactCellLabel(value, department)}</div></td>
          })}</tr>
        })}</tbody>
        {department !== 'quanly' && configuredShiftNames.length > 0 && <tfoot>{configuredShiftNames.map((shift) => <tr key={`summary-${shift}`}><td className="summary-label">Tổng NV · {shift}</td>{days.map((date) => {
          const day = isoDate(date)
          const counts = shiftSummary?.[day]?.[shift] || { regular: 0, overtime: 0, total: 0 }
          const active = highlightedTotal?.day === day && highlightedTotal?.shift === shift
          return <td key={`${shift}-${day}`}><button type="button" className={`shift-total-cell ${active ? 'active' : ''}`} title={`Highlight nhân viên ${shift} ngày ${displayFullDate(date)}`} onClick={() => { setHighlightedEmployee(''); setHighlightedTotal((current) => current?.day === day && current?.shift === shift ? null : { day, shift }) }}><b>{counts.total}</b><small>{counts.regular} chính + {counts.overtime} TC</small></button></td>
        })}</tr>)}</tfoot>}
      </table>
      {!employees.length && <div className="revenue-meta">Không có nhân viên đang hiển thị trong nhóm {DEPARTMENT_INFO[department].label}.</div>}
    </div>}
    {!loading && <div className="schedule-scroll monthly-statistics">
      <h3>THỐNG KÊ THÁNG {month.split('-').reverse().join('/')} · đến hết ngày hôm qua · {DEPARTMENT_INFO[department].label}</h3>
      <table>
        <thead><tr><th>Nhân viên</th><th>Ngày làm việc</th><th>Ngày nghỉ</th><th>Ngày Ca 1</th><th>Ngày Ca 2</th><th>Giờ tăng ca</th></tr></thead>
        <tbody>{monthlyStatistics.rows.map((item) => <tr key={`month-${item.username}`}><td><strong>{item.name}</strong></td><td>{item.workDays}</td><td>{item.offDays}</td><td>{item.ca1Days}</td><td>{item.ca2Days}</td><td>{item.overtimeHours.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}</td></tr>)}</tbody>
        <tfoot><tr><td>Tổng bộ phận {DEPARTMENT_INFO[department].label}</td><td>{monthlyStatistics.departmentTotal.workDays}</td><td>{monthlyStatistics.departmentTotal.offDays}</td><td>{monthlyStatistics.departmentTotal.ca1Days}</td><td>{monthlyStatistics.departmentTotal.ca2Days}</td><td>{monthlyStatistics.departmentTotal.overtimeHours.toLocaleString('vi-VN', { maximumFractionDigits: 2 })}</td></tr></tfoot>
      </table>
    </div>}
    {!loading && comboEditor}
  </section>
}
