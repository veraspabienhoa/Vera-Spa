import { Bell, BellRing, CalendarDays, Download, RefreshCw, Save, Search, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { isApiConfigured, veraApi } from '../lib/api'
import { numberInputDisplayValue } from '../lib/numberInput'
import { playWatchBellSound, unlockWatchBellAudio } from '../lib/watchBell'
import {
  disablePushNotifications,
  enablePushNotifications,
  readPushState,
  syncExistingPushSubscription,
} from '../lib/pushNotifications'
import {
  loadEmployees,
  loadLeaveDailyStats,
  loadLeaveReasons,
  loadLeaveRecords,
} from '../lib/data'

const VIEWED_DATE_FILTER = 'Ngày đang xem'
const STAT_DATE_FILTERS = ['Hôm qua', 'Hôm nay', 'Tuần này', 'Tuần sau', 'Tháng này', 'Tháng sau', 'Tùy chỉnh']
const LIST_DATE_FILTERS = STAT_DATE_FILTERS

const formatDateInput = (date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = () => formatDateInput(new Date())
const addDays = (date, days) => {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}
const formatDateDisplay = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}/${month}/${year}` : ''
}
const weekdayForDate = (value) => {
  const index = new Date(`${value}T00:00:00`).getDay()
  return ['Chủ nhật', 'Thứ 2', 'Thứ 3', 'Thứ 4', 'Thứ 5', 'Thứ 6', 'Thứ 7'][index] || ''
}
const rangeForFilter = (filter) => {
  const now = new Date()
  const monday = addDays(now, -((now.getDay() + 6) % 7))
  if (filter === 'Hôm qua') {
    const yesterday = addDays(now, -1)
    return [formatDateInput(yesterday), formatDateInput(yesterday)]
  }
  if (filter === 'Tuần này') return [formatDateInput(monday), formatDateInput(addDays(monday, 6))]
  if (filter === 'Tuần sau') {
    const nextMonday = addDays(monday, 7)
    return [formatDateInput(nextMonday), formatDateInput(addDays(nextMonday, 6))]
  }
  if (filter === 'Tháng này') {
    return [
      formatDateInput(new Date(now.getFullYear(), now.getMonth(), 1)),
      formatDateInput(new Date(now.getFullYear(), now.getMonth() + 1, 0)),
    ]
  }
  if (filter === 'Tháng sau') {
    return [
      formatDateInput(new Date(now.getFullYear(), now.getMonth() + 1, 1)),
      formatDateInput(new Date(now.getFullYear(), now.getMonth() + 2, 0)),
    ]
  }
  return [today(), today()]
}
const emptyForm = { employee_name: '', leave_reason: '', detail: '', manual_penalty: '' }
const shortEmployeeName = (value) => String(value || '')
  .split(/\s*[-–—]\s*/, 1)[0]
  .trim()
  .toLocaleLowerCase('vi-VN')
  .replace(/(^|\s)\S/g, (letter) => letter.toLocaleUpperCase('vi-VN'))
const normalizeSearch = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()
const matchesEmployeeName = (employeeName, searchValue) => {
  const needle = normalizeSearch(searchValue)
  if (!needle) return true
  return [employeeName, shortEmployeeName(employeeName)].some((name) => normalizeSearch(name) === needle)
}

export default function LeaveRegistrationPage({ user }) {
  const initialRange = useMemo(() => rangeForFilter('Hôm nay'), [])
  const [date, setDate] = useState(today())
  const [rangeFilter, setRangeFilter] = useState('Hôm nay')
  const [rangeStart, setRangeStart] = useState(initialRange[0])
  const [rangeEnd, setRangeEnd] = useState(initialRange[1])
  const [listRangeFilter, setListRangeFilter] = useState('Hôm nay')
  const [listRangeStart, setListRangeStart] = useState(initialRange[0])
  const [listRangeEnd, setListRangeEnd] = useState(initialRange[1])
  const [statsEmployeeSearch, setStatsEmployeeSearch] = useState('')
  const [statsEmployeeFilter, setStatsEmployeeFilter] = useState('')
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [dailyStats, setDailyStats] = useState([])
  const [records, setRecords] = useState([])
  const [reasons, setReasons] = useState([])
  const [employees, setEmployees] = useState([])
  const [selectedUids, setSelectedUids] = useState([])
  const [reasonDrafts, setReasonDrafts] = useState({})
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(false)
  const [saving, setSaving] = useState(false)
  const [managing, setManaging] = useState(false)
  const [message, setMessage] = useState('')
  const [warnings, setWarnings] = useState([])
  const [error, setError] = useState('')
  const [listActionNotice, setListActionNotice] = useState(null)
  const [watchDates, setWatchDates] = useState([])
  const [watchBusyDate, setWatchBusyDate] = useState('')
  const [watchError, setWatchError] = useState('')
  const [watchSoundReady, setWatchSoundReady] = useState(true)
  const [pushState, setPushState] = useState({ loading: true, supported: false, subscribed: false })
  const [pushBusy, setPushBusy] = useState(false)
  const [pushMessage, setPushMessage] = useState('')
  const [exporting, setExporting] = useState(false)
  const [syncingLeaveSource, setSyncingLeaveSource] = useState(false)
  const role = String(user?.role || '').toLowerCase()
  const canChooseEmployee = ['admin', 'quanly', 'letan'].includes(role)
  const canViewPenalty = role === 'admin' || user?.permissions?.employee_penalty_view === true
  const canEdit = role === 'admin'
    || user?.permissions?.leave_manage_edit === true
    || user?.permissions?.leave_detail_edit === true
    || user?.permissions?.leave_today_khong_phep_edit_delete === true
  const canDelete = role === 'admin'
    || user?.permissions?.leave_manage_delete === true
    || user?.permissions?.leave_detail_delete === true
    || user?.permissions?.leave_today_khong_phep_edit_delete === true
  const dateIsPast = role !== 'admin' && date < today()
  const canCreate = isApiConfigured
    && user?.permissions?.leave_create !== false
    && !user?.registration_locked
    && !dateIsPast

  const maxEmployeeDate = useMemo(() => {
    const now = new Date()
    return formatDateInput(new Date(now.getFullYear(), now.getMonth() + 2, 0))
  }, [])

  const refreshWatchDates = useCallback(async () => {
    if (!isApiConfigured) return
    try {
      const result = await veraApi.watchDates()
      setWatchDates(result.watch_dates || [])
      setWatchError('')
    } catch (err) {
      setWatchError(err.message || 'Không tải được các ngày đang quan tâm.')
    }
  }, [])

  const load = useCallback(async () => {
    setBusy(true)
    setError('')
    try {
      if (isApiConfigured) {
        const [dailyData, recordData, reasonData, employeeData] = await Promise.all([
          veraApi.leaveDailyStats(rangeStart, rangeEnd, statsEmployeeFilter),
          veraApi.leaveRecords(listRangeStart, listRangeEnd),
          veraApi.leaveReasons(date),
          veraApi.employees(),
        ])
        setDailyStats(dailyData.days || [])
        const loadedRecords = recordData.records || []
        setRecords(loadedRecords)
        setReasonDrafts(Object.fromEntries(loadedRecords.map((item) => [item.record_uid, item.leave_reason])))
        setSelectedUids([])
        setReasons(reasonData.reasons || [])
        setEmployees(employeeData.employees || [])
      } else {
        const [dailyData, recordData, reasonData, employeeData] = await Promise.all([
          loadLeaveDailyStats(rangeStart, rangeEnd, statsEmployeeFilter),
          loadLeaveRecords(listRangeStart, listRangeEnd),
          loadLeaveReasons(date),
          loadEmployees(),
        ])
        setDailyStats(dailyData)
        setRecords(recordData)
        setReasonDrafts(Object.fromEntries(recordData.map((item) => [item.record_uid, item.leave_reason])))
        setSelectedUids([])
        setReasons(reasonData.map((name) => ({ name, requires_manual_penalty: false })))
        setEmployees(employeeData)
      }
    } catch (err) {
      setError(err.message || 'Không tải được dữ liệu từ PostgreSQL/Supabase.')
    } finally {
      setBusy(false)
    }
  }, [date, listRangeEnd, listRangeStart, rangeEnd, rangeStart, statsEmployeeFilter])

  useEffect(() => { load() }, [load])

  useEffect(() => {
    refreshWatchDates()
    const interval = window.setInterval(refreshWatchDates, 60000)
    const refreshWhenVisible = () => {
      if (document.visibilityState === 'visible') refreshWatchDates()
    }
    window.addEventListener('focus', refreshWatchDates)
    document.addEventListener('visibilitychange', refreshWhenVisible)
    return () => {
      window.clearInterval(interval)
      window.removeEventListener('focus', refreshWatchDates)
      document.removeEventListener('visibilitychange', refreshWhenVisible)
    }
  }, [refreshWatchDates])

  useEffect(() => {
    let active = true
    const refreshPushState = async () => {
      try {
        const state = await syncExistingPushSubscription()
        if (active) setPushState({ ...state, loading: false })
      } catch {
        try {
          const state = await readPushState()
          if (active) setPushState({ ...state, loading: false })
        } catch (err) {
          if (active) setPushState({ loading: false, supported: false, subscribed: false, reason: err.message })
        }
      }
    }
    void refreshPushState()
    return () => { active = false }
  }, [])

  useEffect(() => {
    if (canChooseEmployee || !user?.employee_username) return
    setForm((current) => ({ ...current, employee_name: user.employee_username }))
  }, [canChooseEmployee, user?.employee_username])

  useEffect(() => {
    setForm((current) => current.leave_reason && !reasons.some((item) => item.name === current.leave_reason)
      ? { ...current, leave_reason: '', manual_penalty: '' }
      : current)
  }, [reasons])

  const filteredRecords = useMemo(() => {
    if (!normalizeSearch(employeeSearch)) return records
    return records.filter((item) => matchesEmployeeName(item.employee_name, employeeSearch))
  }, [employeeSearch, records])
  const watchedDateSet = useMemo(() => new Set(watchDates.map((item) => item.date)), [watchDates])
  const unreadWatchDates = useMemo(() => watchDates.filter((item) => item.has_unread), [watchDates])
  const unreadWatchDateSet = useMemo(() => new Set(unreadWatchDates.map((item) => item.date)), [unreadWatchDates])
  const unreadWatchKey = useMemo(() => unreadWatchDates.map((item) => item.date).sort().join('|'), [unreadWatchDates])
  const totalPenalty = useMemo(
    () => filteredRecords.reduce((sum, item) => sum + Number(item.penalty || 0), 0),
    [filteredRecords],
  )
  const statsTotalPenalty = useMemo(
    () => dailyStats.reduce((sum, item) => sum + Number(item.total_penalty || 0), 0),
    [dailyStats],
  )
  const selectedReason = useMemo(() => reasons.find((item) => item.name === form.leave_reason), [reasons, form.leave_reason])
  const changedRecords = useMemo(
    () => records.filter((item) => reasonDrafts[item.record_uid] && reasonDrafts[item.record_uid] !== item.leave_reason),
    [reasonDrafts, records],
  )

  const ringWatchBell = useCallback(async () => {
    const played = await playWatchBellSound()
    setWatchSoundReady(played)
    return played
  }, [])

  useEffect(() => {
    if (!unreadWatchKey) {
      setWatchSoundReady(true)
      return undefined
    }

    void ringWatchBell()
    const bellInterval = window.setInterval(ringWatchBell, 5000)
    const unlockAndRing = () => {
      void unlockWatchBellAudio().then(() => ringWatchBell())
    }
    window.addEventListener('pointerdown', unlockAndRing, { once: true })
    window.addEventListener('keydown', unlockAndRing, { once: true })
    return () => {
      window.clearInterval(bellInterval)
      window.removeEventListener('pointerdown', unlockAndRing)
      window.removeEventListener('keydown', unlockAndRing)
    }
  }, [ringWatchBell, unreadWatchKey])

  const toggleSelected = (recordUid) => {
    setSelectedUids((current) => current.includes(recordUid)
      ? current.filter((uid) => uid !== recordUid)
      : [...current, recordUid])
  }

  const toggleWatchDate = async (targetDate) => {
    if (!isApiConfigured || watchBusyDate) return
    setWatchBusyDate(targetDate)
    setWatchError('')
    try {
      await veraApi.setWatchDate(targetDate, !watchedDateSet.has(targetDate))
      await refreshWatchDates()
    } catch (err) {
      setWatchError(err.message || 'Không cập nhật được ngày quan tâm.')
    } finally {
      setWatchBusyDate('')
    }
  }

  const acknowledgeWatchDate = async (targetDate) => {
    setWatchBusyDate(targetDate)
    setWatchError('')
    try {
      await veraApi.acknowledgeWatchDates([targetDate])
      await refreshWatchDates()
    } catch (err) {
      setWatchError(err.message || 'Không xác nhận được thông báo.')
    } finally {
      setWatchBusyDate('')
    }
  }

  const saveEdits = async () => {
    if (!canEdit || changedRecords.length === 0) return
    const updatedCount = changedRecords.length
    setManaging(true)
    setListActionNotice(null)
    try {
      for (const item of changedRecords) {
        const nextReason = reasons.find((reason) => reason.name === reasonDrafts[item.record_uid])
        const payload = { leave_reason: reasonDrafts[item.record_uid] }
        if (nextReason?.requires_manual_penalty) {
          const amount = window.prompt(`Nhập mức phạt cho "${nextReason.name}" (VNĐ):`, '')
          if (amount === null) throw new Error('Đã hủy thao tác sửa vì chưa nhập mức phạt.')
          const parsed = Number(String(amount).replace(/[^0-9.-]/g, ''))
          if (!Number.isFinite(parsed) || parsed < 0) throw new Error('Mức phạt phải là số không âm.')
          payload.manual_penalty = parsed
        }
        await veraApi.updateLeave(item.record_uid, payload)
      }
      await load()
      await refreshWatchDates()
      setListActionNotice({
        action: 'edit',
        status: 'success',
        message: `Đã cập nhật ${updatedCount} lịch nghỉ.`,
      })
    } catch (err) {
      setListActionNotice({
        action: 'edit',
        status: 'error',
        message: err.message || 'Không sửa được lịch nghỉ.',
      })
    } finally {
      setManaging(false)
    }
  }

  const deleteSelected = async () => {
    if (!canDelete || selectedUids.length === 0) return
    if (!window.confirm(`Xóa ${selectedUids.length} lịch nghỉ đã chọn?`)) return
    const deletedCount = selectedUids.length
    setManaging(true)
    setListActionNotice(null)
    try {
      await veraApi.deleteLeaves(selectedUids)
      await load()
      await refreshWatchDates()
      setListActionNotice({
        action: 'delete',
        status: 'success',
        message: `Đã xóa ${deletedCount} lịch nghỉ đã chọn.`,
      })
    } catch (err) {
      setListActionNotice({
        action: 'delete',
        status: 'error',
        message: err.message || 'Không xóa được lịch nghỉ.',
      })
    } finally {
      setManaging(false)
    }
  }

  const togglePushNotifications = async () => {
    if (pushBusy) return
    setPushBusy(true)
    setPushMessage('')
    setWatchError('')
    try {
      const nextState = pushState.subscribed
        ? await disablePushNotifications()
        : await enablePushNotifications()
      setPushState({ ...nextState, loading: false })
      setPushMessage(nextState.subscribed
        ? 'Đã bật thông báo màn hình khóa cho thiết bị này.'
        : 'Đã tắt thông báo màn hình khóa trên thiết bị này.')
    } catch (err) {
      setWatchError(err.message || 'Không cập nhật được thông báo màn hình khóa.')
      const state = await readPushState().catch(() => pushState)
      setPushState({ ...state, loading: false })
    } finally {
      setPushBusy(false)
    }
  }

  const exportExcel = async () => {
    if (role !== 'admin' || exporting) return
    setExporting(true)
    setError('')
    try {
      await veraApi.exportLeaveExcel(listRangeStart, listRangeEnd, employeeSearch)
    } catch (err) {
      setError(err.message || 'Không xuất được danh sách Excel.')
    } finally {
      setExporting(false)
    }
  }

  const syncLeaveSource = async () => {
    if (!['admin', 'quanly', 'letan'].includes(role) || syncingLeaveSource) return
    if (!window.confirm('Đồng bộ các lịch nghỉ còn thiếu từ Web V2 vào LichNghi_VeraSpa?\n\nDòng đã có và dòng Vi phạm sẽ được bỏ qua.')) return
    setSyncingLeaveSource(true)
    setError('')
    try {
      const result = await veraApi.syncLeaveSource()
      setMessage(result.message || 'Đã đồng bộ LichNghi_VeraSpa.')
    } catch (err) {
      setError(err.message || 'Không đồng bộ được LichNghi_VeraSpa.')
    } finally {
      setSyncingLeaveSource(false)
    }
  }

  const chooseRangeFilter = (filter) => {
    setRangeFilter(filter)
    if (filter === 'Tùy chỉnh') return
    const [start, end] = rangeForFilter(filter)
    setRangeStart(start)
    setRangeEnd(end)
    setDate(filter === 'Hôm nay' || filter === 'Tháng này' || filter === 'Tuần này' ? today() : start)
  }

  const changeCustomStart = (value) => {
    setRangeStart(value)
    if (value > rangeEnd) setRangeEnd(value)
    setDate(value)
  }

  const changeCustomEnd = (value) => {
    setRangeEnd(value)
    if (value < rangeStart) {
      setRangeStart(value)
      setDate(value)
    }
  }

  const chooseListRangeFilter = (filter) => {
    setListRangeFilter(filter)
    setSelectedUids([])
    if (filter === VIEWED_DATE_FILTER) {
      setListRangeStart(date)
      setListRangeEnd(date)
      return
    }
    if (filter === 'Tùy chỉnh') return
    const [start, end] = rangeForFilter(filter)
    setListRangeStart(start)
    setListRangeEnd(end)
  }

  const changeListCustomStart = (value) => {
    setSelectedUids([])
    setListRangeStart(value)
    if (value > listRangeEnd) setListRangeEnd(value)
  }

  const changeListCustomEnd = (value) => {
    setSelectedUids([])
    setListRangeEnd(value)
    if (value < listRangeStart) setListRangeStart(value)
  }

  const selectViewedDate = (value) => {
    setDate(value)
    setRangeFilter(VIEWED_DATE_FILTER)
    setRangeStart(value)
    setRangeEnd(value)
    setListRangeFilter(VIEWED_DATE_FILTER)
    setListRangeStart(value)
    setListRangeEnd(value)
    setSelectedUids([])
  }

  const submit = async (event) => {
    event.preventDefault()
    setMessage('')
    setWarnings([])
    setError('')
    if (!canCreate) {
      setError(dateIsPast
        ? 'Không được đăng ký lịch nghỉ cho ngày trong quá khứ.'
        : user?.registration_locked
          ? 'Quyền đăng ký nghỉ của vai trò này đang bị Admin tạm khóa.'
          : 'Tài khoản hiện tại chưa được cấp quyền ghi lịch nghỉ.')
      return
    }
    setSaving(true)
    try {
      const payload = {
        employee_name: form.employee_name,
        leave_reason: form.leave_reason,
        detail: form.detail,
        leave_date: date,
      }
      if (selectedReason?.requires_manual_penalty) {
        if (form.manual_penalty === '') throw new Error('Lý do này bắt buộc nhập Mức phạt vi phạm.')
        payload.manual_penalty = Number(form.manual_penalty)
      }
      const result = await veraApi.createLeave(payload)
      setForm({
        ...emptyForm,
        employee_name: canChooseEmployee ? '' : (user?.employee_username || ''),
      })
      setWarnings(result.warnings || [])
      setMessage('Đã ghi lịch nghỉ THÀNH CÔNG')
      await load()
      await refreshWatchDates()
    } catch (err) {
      setError(`KHÔNG THÀNH CÔNG (${err.message || 'Không ghi được lịch nghỉ.'})`)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div>
      <div className="page-heading-row">
        <div><h1 className="page-title">Đăng ký nghỉ</h1></div>
        <button className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /> Làm mới</button>
      </div>

      {!isApiConfigured && (
        <div className="warning-box"><strong>Chế độ chỉ đọc.</strong> API chưa được cấu hình nên nút Ghi đang khóa an toàn.</div>
      )}

      {isApiConfigured && user?.registration_locked && (
        <div className="warning-box"><strong>Đang khóa đăng ký.</strong> Admin đang tạm khóa quyền đăng ký nghỉ của vai trò {role}.</div>
      )}

      {isApiConfigured && user?.permissions?.leave_create === false && (
        <div className="warning-box"><strong>Chế độ chỉ xem.</strong> Tài khoản này chưa được cấp quyền ghi lịch nghỉ.</div>
      )}

      <div className="date-toolbar viewed-date-toolbar">
        <DatePickerControl
          label="Ngày đang xem"
          value={date}
          onChange={selectViewedDate}
          max={role === 'admin' ? undefined : maxEmployeeDate}
        />
        <button
          type="button"
          className={`watch-current-date-button ${watchedDateSet.has(date) ? 'active' : ''} ${unreadWatchDateSet.has(date) ? 'ringing' : ''}`}
          onClick={() => toggleWatchDate(date)}
          disabled={!isApiConfigured || Boolean(watchBusyDate)}
          aria-pressed={watchedDateSet.has(date)}
        >
          {watchedDateSet.has(date) ? <BellRing size={17} /> : <Bell size={17} />}
          {watchedDateSet.has(date) ? 'Đang quan tâm ngày này' : 'Quan tâm ngày này'}
        </button>
        <button
          type="button"
          className={`push-toggle-button ${pushState.subscribed ? 'active' : ''}`}
          onClick={togglePushNotifications}
          disabled={pushBusy || pushState.loading || !pushState.supported}
        >
          {pushState.subscribed ? <BellRing size={17} /> : <Bell size={17} />}
          {pushState.loading
            ? 'Đang kiểm tra thông báo…'
            : pushState.subscribed
              ? 'Thông báo màn hình khóa: Đã bật'
              : 'Bật thông báo màn hình khóa'}
        </button>
        {!pushState.loading && !pushState.supported && pushState.reason && (
          <span className="push-support-note">{pushState.reason}</span>
        )}
      </div>

      {pushMessage && <div className="success-box push-status-box">{pushMessage}</div>}

      {unreadWatchDates.length > 0 && (
        <section className="watch-notification-panel ringing" role="alert" aria-live="assertive">
          <div className="watch-notification-heading">
            <button type="button" className="watch-ringing-button" onClick={ringWatchBell} aria-label="Phát lại chuông thông báo">
              <BellRing className="watch-ringing-icon" size={19} />
            </button>
            <div>
              <strong>Ngày bạn quan tâm vừa có thay đổi</strong>
              <span>Chỉ thông báo thay đổi từ 6 lý do nghỉ CÓ phép đã quy định.</span>
              {!watchSoundReady && <span className="watch-sound-hint">Chạm biểu tượng chuông để bật âm thanh.</span>}
            </div>
          </div>
          <div className="watch-notification-list">
            {unreadWatchDates.map((item) => (
              <div className="watch-notification-item" key={item.date}>
                <span>
                  <strong>{formatDateDisplay(item.date)}</strong>: số nhân viên đăng ký nghỉ CÓ phép đã thay đổi
                  {item.last_seen_paid_count !== item.current_paid_count
                    ? ` từ ${item.last_seen_paid_count} thành ${item.current_paid_count}.`
                    : `; hiện có ${item.current_paid_count}.`}
                </span>
                <button type="button" onClick={() => acknowledgeWatchDate(item.date)} disabled={watchBusyDate === item.date}>
                  Đã xem
                </button>
              </div>
            ))}
          </div>
        </section>
      )}

      {watchError && <div className="error-box watch-error-box">{watchError}</div>}

      <div className="content-grid">
        <section className="panel registration-panel">
          <div className="panel-title-row">
            <div><h2>ĐĂNG KÝ MỚI</h2></div>
          </div>
          <form className="leave-form" onSubmit={submit}>
            <label>Tên nhân viên</label>
            <select
              value={form.employee_name}
              onChange={(e) => setForm((current) => ({ ...current, employee_name: e.target.value }))}
              disabled={!canChooseEmployee}
              required
            >
              <option value="">-- Chọn nhân viên --</option>
              {employees.map((employee) => (
                <option key={employee.username} value={employee.username}>
                  {shortEmployeeName(employee.username)}
                </option>
              ))}
            </select>

            <label>Lý do nghỉ</label>
            <select
              value={form.leave_reason}
              onChange={(e) => {
                const leaveReason = e.target.value
                setForm((current) => ({ ...current, leave_reason: leaveReason, manual_penalty: '' }))
              }}
              required
            >
              <option value="">-- Chọn lý do nghỉ --</option>
              {reasons.map((reason) => <option key={reason.name} value={reason.name}>{reason.name}</option>)}
            </select>

            {selectedReason && !selectedReason.requires_manual_penalty && (
              <div className="info-box">
                Số ngày tính: <strong>{selectedReason.days ?? 0}</strong>
                {canViewPenalty && selectedReason.penalty !== null && selectedReason.penalty !== undefined && (
                  <> · Phạt nền: <strong>{Number(selectedReason.penalty || 0).toLocaleString('vi-VN')}đ</strong></>
                )}
              </div>
            )}

            {selectedReason?.requires_manual_penalty && (
              <>
                <label>Mức phạt vi phạm</label>
                <input
                  type="number"
                  min="0"
                  step="1000"
                  value={numberInputDisplayValue(form.manual_penalty)}
                  onChange={(e) => setForm((current) => ({ ...current, manual_penalty: e.target.value }))}
                  placeholder="Nhập số tiền"
                  required
                />
              </>
            )}

            <label>Chi tiết</label>
            <textarea value={form.detail} onChange={(e) => setForm((current) => ({ ...current, detail: e.target.value }))} rows="3" placeholder="Ghi chú nếu cần" />

            {dateIsPast && <div className="warning-box"><strong>Ngày chỉ xem.</strong> Nhân viên không thể đăng ký cho ngày trong quá khứ.</div>}
            {message && <div className="success-box">{message}</div>}
            {warnings.map((warning) => <div className="warning-box" key={warning}>{warning}</div>)}
            {error && <div className="error-box">{error}</div>}
            <button className="primary-button" type="submit" disabled={saving || !canCreate}>{saving ? 'Đang kiểm tra & ghi…' : 'Ghi'}</button>
          </form>
        </section>

        <section className="panel daily-summary-panel">
          <div className="panel-title-row">
            <div>
              <h2>THỐNG KÊ</h2>
              <p>
                Ngày đang xem: {formatDateDisplay(date)} · Bộ lọc {formatDateDisplay(rangeStart)} – {formatDateDisplay(rangeEnd)}
                {statsEmployeeFilter ? ` · Nhân viên: ${statsEmployeeFilter}` : ''}.
              </p>
            </div>
            <div className="list-actions statistics-title-actions">
              {canViewPenalty && <div className="penalty-chip">Tổng tiền phạt: {statsTotalPenalty.toLocaleString('vi-VN')}đ</div>}
              <button type="button" className="secondary-button compact" onClick={load} disabled={busy}>
                <RefreshCw size={15} className={busy ? 'spin' : ''} /> Làm mới
              </button>
            </div>
          </div>
          <div className="list-filter-toolbar statistics-filter-toolbar">
            <div className="range-filter-buttons list-range-buttons" role="group" aria-label="Lọc thời gian thống kê">
              {STAT_DATE_FILTERS.map((filter) => (
                <button
                  type="button"
                  key={filter}
                  className={rangeFilter === filter ? 'active' : ''}
                  onClick={() => chooseRangeFilter(filter)}
                >
                  {filter}
                </button>
              ))}
            </div>
            {rangeFilter === 'Tùy chỉnh' && (
              <div className="custom-range list-custom-range statistics-custom-range">
                <DatePickerControl label="Từ ngày" value={rangeStart} onChange={changeCustomStart} />
                <DatePickerControl label="Đến ngày" value={rangeEnd} onChange={changeCustomEnd} />
              </div>
            )}
            <div className="statistics-employee-search">
              <label className="employee-search-field statistics-employee-search-field">
                <span><Search size={15} aria-hidden="true" /> Tên nhân viên</span>
                <input
                  type="search"
                  value={statsEmployeeSearch}
                  onChange={(event) => setStatsEmployeeSearch(event.target.value)}
                  onKeyDown={(event) => {
                    if (event.key === 'Enter') {
                      event.preventDefault()
                      setStatsEmployeeFilter(statsEmployeeSearch.trim())
                    }
                  }}
                  placeholder="Nhập tên nhân viên"
                  aria-label="Tìm kiếm tên nhân viên trong thống kê"
                  list="statistics-employee-options"
                />
              </label>
              <datalist id="statistics-employee-options">
                {employees.map((employee) => <option key={employee.username} value={employee.username}>{shortEmployeeName(employee.username)}</option>)}
              </datalist>
              <div className="statistics-search-actions">
                <button type="button" className="secondary-button compact" onClick={() => setStatsEmployeeFilter(statsEmployeeSearch.trim())} disabled={busy}>
                  <Search size={14} /> Tìm
                </button>
                {(statsEmployeeFilter || statsEmployeeSearch) && (
                  <button
                    type="button"
                    className="secondary-button compact"
                    onClick={() => {
                      setStatsEmployeeSearch('')
                      setStatsEmployeeFilter('')
                    }}
                    disabled={busy}
                  >
                    <X size={14} /> Bỏ lọc
                  </button>
                )}
              </div>
            </div>
          </div>
          <div className="table-wrap daily-summary-wrap">
            <table className={`daily-summary-table ${canViewPenalty ? 'with-penalty' : 'without-penalty'}`}>
              <colgroup>
                <col className="daily-col-date" />
                <col className="daily-col-weekday" />
                <col className="daily-col-total" />
                <col className="daily-col-paid" />
                <col className="daily-col-generated" />
                <col className="daily-col-unpaid" />
                {canViewPenalty && <col className="daily-col-penalty" />}
              </colgroup>
              <thead>
                <tr>
                  <th>Ngày</th>
                  <th><span className="full-column-label">Thứ ngày</span><span className="compact-column-label">Thứ</span></th>
                  <th className="center"><span className="full-column-label">Tổng nghỉ</span><span className="compact-column-label">Nghỉ</span></th>
                  <th className="center"><span className="full-column-label">✅ Có phép</span><span className="compact-column-label">Phép</span></th>
                  <th className="center"><span className="full-column-label">⚠️ Phát sinh</span><span className="compact-column-label">PS</span></th>
                  <th className="center"><span className="full-column-label">❌ Không phép</span><span className="compact-column-label">K.phép</span></th>
                  {canViewPenalty && <th className="right"><span className="full-column-label">💰 Tổng tiền phạt</span><span className="compact-column-label">Phạt</span></th>}
                </tr>
              </thead>
              <tbody>
                {dailyStats.length === 0 ? (
                  <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell">{statsEmployeeFilter ? `Không có dữ liệu của ${statsEmployeeFilter} trong khoảng thời gian này.` : 'Không có dữ liệu trong khoảng thời gian này.'}</td></tr>
                ) : dailyStats.map((day) => (
                  <tr key={day.date} className={day.date === date ? 'selected-day-row' : ''}>
                    <td>
                      <div className="daily-date-actions">
                        <button type="button" className="date-link" onClick={() => selectViewedDate(day.date)}>
                          {formatDateDisplay(day.date)}
                        </button>
                        <button
                          type="button"
                          className={`watch-date-icon ${watchedDateSet.has(day.date) ? 'active' : ''} ${unreadWatchDateSet.has(day.date) ? 'ringing' : ''}`}
                          onClick={() => toggleWatchDate(day.date)}
                          disabled={Boolean(watchBusyDate)}
                          aria-label={watchedDateSet.has(day.date) ? `Bỏ quan tâm ngày ${formatDateDisplay(day.date)}` : `Quan tâm ngày ${formatDateDisplay(day.date)}`}
                          aria-pressed={watchedDateSet.has(day.date)}
                        >
                          {watchedDateSet.has(day.date) ? <BellRing size={14} /> : <Bell size={14} />}
                        </button>
                      </div>
                    </td>
                    <td>{day.weekday_label}</td>
                    <td className="center"><span className="daily-stat-value">{day.total_leave}</span></td>
                    <td className="center"><span className={`daily-stat-value paid-stat ${day.paid_full ? 'paid-limit-full' : ''}`}>{day.paid}</span></td>
                    <td className="center"><span className="daily-stat-value">{day.generated}</span></td>
                    <td className="center"><span className="daily-stat-value">{day.unpaid}</span></td>
                    {canViewPenalty && <td className="money-cell right">{Number(day.total_penalty || 0).toLocaleString('vi-VN')}đ</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>

        <section className="panel leave-list-panel">
          <div className="panel-title-row">
            <div>
              <h2>DANH SÁCH</h2>
              <p>
                Ngày đang xem: {formatDateDisplay(date)} · Bộ lọc {formatDateDisplay(listRangeStart)} – {formatDateDisplay(listRangeEnd)} · {' '}
                {listRangeStart === listRangeEnd
                  ? `${weekdayForDate(listRangeStart)} có ${filteredRecords.length} lịch nghỉ.`
                  : `Có ${filteredRecords.length} lịch nghỉ.`}
              </p>
            </div>
            <button type="button" className="secondary-button compact" onClick={load} disabled={busy}>
              <RefreshCw size={15} className={busy ? 'spin' : ''} /> Làm mới
            </button>
          </div>
          <div className="list-actions">
              {['admin', 'quanly', 'letan'].includes(role) && user?.permissions?.leave_export !== false && <button type="button" className="secondary-button compact export-button" onClick={syncLeaveSource} disabled={syncingLeaveSource}><RefreshCw size={15} className={syncingLeaveSource ? 'spin' : ''} /> {syncingLeaveSource ? 'Đang đồng bộ…' : 'Đồng bộ Web V2 → LichNghi_VeraSpa'}</button>}
              {role === 'admin' && <button type="button" className="secondary-button compact export-button" onClick={exportExcel} disabled={exporting}><Download size={15} /> {exporting ? 'Đang xuất…' : 'Export to Excel'}</button>}
              {canEdit && <button type="button" className="secondary-button compact" onClick={saveEdits} disabled={managing || changedRecords.length === 0}><Save size={15} /> Lưu sửa</button>}
              {canDelete && <button type="button" className="danger-button compact" onClick={deleteSelected} disabled={managing || selectedUids.length === 0}><Trash2 size={15} /> Xóa đã chọn</button>}
              {canViewPenalty && <div className="penalty-chip">Phạt: {totalPenalty.toLocaleString('vi-VN')}đ</div>}
          </div>
          {listActionNotice && (
            <div
              className={`list-action-notice ${listActionNotice.status} ${listActionNotice.action}`}
              role={listActionNotice.status === 'error' ? 'alert' : 'status'}
              aria-live="polite"
            >
              <div className="list-action-notice-icon" aria-hidden="true">
                {listActionNotice.action === 'edit' ? <Save size={17} /> : <Trash2 size={17} />}
              </div>
              <div className="list-action-notice-copy">
                <strong>
                  {listActionNotice.action === 'edit'
                    ? (listActionNotice.status === 'success' ? 'LƯU SỬA THÀNH CÔNG' : 'LƯU SỬA KHÔNG THÀNH CÔNG')
                    : (listActionNotice.status === 'success' ? 'XÓA ĐÃ CHỌN THÀNH CÔNG' : 'XÓA ĐÃ CHỌN KHÔNG THÀNH CÔNG')}
                </strong>
                <span>{listActionNotice.message}</span>
              </div>
              <button type="button" className="list-action-notice-close" onClick={() => setListActionNotice(null)} aria-label="Đóng thông báo">
                <X size={15} />
              </button>
            </div>
          )}
          <div className="list-filter-toolbar">
            <div className="range-filter-buttons list-range-buttons" role="group" aria-label="Lọc thời gian danh sách">
              {LIST_DATE_FILTERS.map((filter) => (
                <button
                  type="button"
                  key={filter}
                  className={listRangeFilter === filter ? 'active' : ''}
                  onClick={() => chooseListRangeFilter(filter)}
                >
                  {filter}
                </button>
              ))}
            </div>
            {listRangeFilter === 'Tùy chỉnh' && (
              <div className="custom-range list-custom-range">
                <DatePickerControl label="Từ ngày" value={listRangeStart} onChange={changeListCustomStart} />
                <DatePickerControl label="Đến ngày" value={listRangeEnd} onChange={changeListCustomEnd} />
              </div>
            )}
            <label className="employee-search-field">
              <span><Search size={15} aria-hidden="true" /> Tên nhân viên</span>
              <input
                type="search"
                value={employeeSearch}
                onChange={(event) => {
                  setEmployeeSearch(event.target.value)
                  setSelectedUids([])
                }}
                placeholder="Chọn hoặc nhập đúng tên nhân viên"
                aria-label="Tìm kiếm tên nhân viên"
                list="list-employee-options"
              />
            </label>
            <datalist id="list-employee-options">
              {employees.map((employee) => <option key={employee.username} value={employee.username}>{shortEmployeeName(employee.username)}</option>)}
            </datalist>
          </div>
          <div className="table-wrap leave-list-wrap">
            <table className={`leave-records-table ${canViewPenalty ? 'with-penalty' : 'without-penalty'}`}>
              <colgroup>
                <col className="leave-col-select" />
                <col className="leave-col-date" />
                <col className="leave-col-weekday" />
                <col className="leave-col-employee" />
                <col className="leave-col-reason" />
                <col className="leave-col-detail" />
                {canViewPenalty && <col className="leave-col-penalty" />}
              </colgroup>
              <thead><tr><th className="select-column">Chọn</th><th>Ngày</th><th>Thứ</th><th>Nhân viên</th><th>Lý do</th><th>Chi tiết</th>{canViewPenalty && <th className="right">Phạt</th>}</tr></thead>
              <tbody>
                {filteredRecords.length === 0 ? (
                  <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell">Không có lịch nghỉ phù hợp bộ lọc.</td></tr>
                ) : filteredRecords.map((item) => (
                  <tr key={item.record_uid || `${item.employee_name}-${item.leave_reason}`}>
                    <td className="select-column"><input type="checkbox" aria-label={`Chọn lịch của ${shortEmployeeName(item.employee_name)}`} checked={selectedUids.includes(item.record_uid)} onChange={() => toggleSelected(item.record_uid)} disabled={!canDelete || managing} /></td>
                    <td><button type="button" className="date-link list-date-link" onClick={() => selectViewedDate(item.leave_date)}>{formatDateDisplay(item.leave_date)}</button></td>
                    <td className="weekday-cell">{item.weekday_label || weekdayForDate(item.leave_date)}</td>
                    <td><strong>{shortEmployeeName(item.employee_name)}</strong></td>
                    <td className="reason-edit-cell">
                      {canEdit && item.leave_date === date ? (
                        <select value={reasonDrafts[item.record_uid] || item.leave_reason} onChange={(event) => setReasonDrafts((current) => ({ ...current, [item.record_uid]: event.target.value }))} disabled={managing}>
                          {!reasons.some((reason) => reason.name === item.leave_reason) && <option value={item.leave_reason}>{item.leave_reason}</option>}
                          {reasons.map((reason) => <option key={reason.name} value={reason.name}>{reason.name}</option>)}
                        </select>
                      ) : <span title={canEdit ? 'Chọn ngày ở cột Ngày để sửa lý do.' : undefined}>{item.leave_reason}</span>}
                    </td>
                    <td className="detail-cell">{item.detail || '—'}</td>
                    {canViewPenalty && <td className="right">{Number(item.penalty || 0).toLocaleString('vi-VN')}đ</td>}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>

    </div>
  )
}

function DatePickerControl({ label, value, onChange, min, max }) {
  return (
    <div className="date-input-group">
      <span className="date-input-label">{label}</span>
      <label className="date-picker-control">
        <span>{formatDateDisplay(value)}</span>
        <CalendarDays size={18} aria-hidden="true" />
        <input
          className="date-picker-native"
          type="date"
          aria-label={label}
          value={value}
          min={min}
          max={max}
          onChange={(event) => onChange(event.target.value)}
        />
      </label>
    </div>
  )
}
