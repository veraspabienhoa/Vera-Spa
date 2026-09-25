import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import useAutoSave from '../hooks/useAutoSave'
import ClearableSearchInput from '../components/ClearableSearchInput'
import VeraDateInput from '../components/VeraDateInput'
import { Bell, BellRing, CalendarDays, Download, RefreshCw, Save, Search, Trash2, X } from 'lucide-react'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { createLeavePageLoader } from '../lib/leavePageLoader'
import { leaveMonthRange } from '../lib/leaveMonthRange'
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
import {
  canChangeLeaveReason,
  canDeleteLeaveRecord,
  canEditLeaveRecord,
  EMPLOYEE_SELF_SERVICE_ROLES,
  letanReasonChoices,
} from '../lib/leaveRecordPermissions'

const VIEWED_DATE_FILTER = 'Ngày đang xem'
const STAT_DATE_FILTERS = ['Hôm qua', 'Hôm nay', 'Tuần này', 'Tuần sau', 'Tháng này', 'Tháng sau', 'Tùy chỉnh']
const LIST_DATE_FILTERS = STAT_DATE_FILTERS

const formatDateInput = (date) => {
  const year = date.getFullYear()
  const month = `${date.getMonth() + 1}`.padStart(2, '0')
  const day = `${date.getDate()}`.padStart(2, '0')
  return `${year}-${month}-${day}`
}

const today = () => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date())
const addDays = (date, days) => {
  const next = new Date(date)
  next.setDate(next.getDate() + days)
  return next
}
const formatDateDisplay = (value) => {
  const [year, month, day] = String(value || '').split('-')
  return year && month && day ? `${day}-${month}-${year}` : ''
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
  const [requestedRangeStart, setRangeStart] = useState(initialRange[0])
  const [requestedRangeEnd, setRangeEnd] = useState(initialRange[1])
  const [listRangeFilter, setListRangeFilter] = useState('Hôm nay')
  const [requestedListRangeStart, setListRangeStart] = useState(initialRange[0])
  const [requestedListRangeEnd, setListRangeEnd] = useState(initialRange[1])
  const activeMonth = date.slice(0, 7)
  const [rangeStart, rangeEnd] = leaveMonthRange(activeMonth, requestedRangeStart, requestedRangeEnd)
  const [listRangeStart, listRangeEnd] = leaveMonthRange(activeMonth, requestedListRangeStart, requestedListRangeEnd)
  const [statsEmployeeSearch, setStatsEmployeeSearch] = useState('')
  const [statsEmployeeFilter, setStatsEmployeeFilter] = useState('')
  const [employeeSearch, setEmployeeSearch] = useState('')
  const [dailyStats, setDailyStats] = useState([])
  const [records, setRecords] = useState([])
  const [reasons, setReasons] = useState([])
  const [recordReasonsByDate, setRecordReasonsByDate] = useState({})
  const [recordReasonErrors, setRecordReasonErrors] = useState({})
  const [employeeSelfServicePolicy, setEmployeeSelfServicePolicy] = useState({
    enabled: true, regular_notice_days: 3, unpaid_notice_days: 1,
  })
  const [letanLeavePolicy, setLetanLeavePolicy] = useState({ enabled: true })
  const [employees, setEmployees] = useState([])
  const [selectedUids, setSelectedUids] = useState([])
  const leaveFormRef = useRef(null)
  const leavePageRef = useRef(null)
  const mutationRef = useRef(false)
  const [reasonDrafts, setReasonDrafts] = useState({})
  const [form, setForm] = useState(emptyForm)
  const [busy, setBusy] = useState(true)
  const [loadState, setLoadState] = useState({ daily: 'loading', records: 'loading', reasons: 'loading', employees: 'loading' })
  const pageLoader = useRef(null)
  const latestLoad = useRef(null)
  if (!pageLoader.current) pageLoader.current = createLeavePageLoader()
  const recordReasonsRef = useRef({})
  const recordReasonsRevision = useRef(0)
  const pendingReasonDates = useRef(new Set())
  const identityKey = JSON.stringify([user?.employee_username, user?.role, user?.permissions])
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
  const role = String(user?.role || '').toLowerCase()
  const employeeSelfService = EMPLOYEE_SELF_SERVICE_ROLES.has(role) && employeeSelfServicePolicy.enabled !== false
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
  const recordPermissionContext = (item) => ({
    role,
    allowedByPermission: canEdit,
    recordDate: item?.leave_date,
    currentReason: item?.leave_reason,
    currentLeaveType: item?.leave_type,
    today: today(),
    isOwnRecord: normalizeSearch(item?.employee_name) === normalizeSearch(user?.employee_username),
    employeeSelfServicePolicy,
    letanLeavePolicy,
  })
  const canEditRecord = (item) => canEditLeaveRecord(recordPermissionContext(item))
  const canDeleteRecord = (item) => canDeleteLeaveRecord({ ...recordPermissionContext(item), allowedByPermission: canDelete })
  const dateIsPast = role !== 'admin' && date < today()
  const canCreate = isApiConfigured
    && loadState.reasons === 'ready' && loadState.employees === 'ready'
    && (employeeSelfService || user?.permissions?.leave_create !== false)
    && !user?.registration_locked
    && !dateIsPast
  const registrationEmployees = useMemo(() => employees.filter((employee) => {
    const employeeRole = String(employee?.role || '').trim().toLowerCase()
    const employmentStatus = employee?.employment_status ?? employee?.['Trạng thái làm việc']
    const isWorking = !employmentStatus || normalizeSearch(employmentStatus) === 'dang lam viec'
    return ['leader', 'nhanvien'].includes(employeeRole) && isWorking
  }), [employees])

  const maxEmployeeDate = useMemo(() => {
    const now = new Date()
    return formatDateInput(new Date(now.getFullYear(), now.getMonth() + 2, 0))
  }, [])

  const refreshWatchDates = useCallback(async () => {
    if (!isApiConfigured) return
    try {
      const [result, notificationResult] = await Promise.all([
        veraApi.watchDates(),
        veraApi.notificationSettings().catch(() => ({ settings: [] })),
      ])
      const setting = (notificationResult.settings || []).find((item) => item.key === 'leave_watch')
      setWatchDates(setting?.enabled === false
        ? (result.watch_dates || []).map((item) => ({ ...item, has_unread: false }))
        : (result.watch_dates || []))
      setWatchError('')
    } catch (err) {
      setWatchError(err.message || 'Không tải được các ngày đang quan tâm.')
    }
  }, [])

  const load = useCallback(async (options = {}) => {
    const afterSave = options?.afterSave === true
    const sources = { daily: 'thống kê lịch nghỉ', records: 'danh sách lịch nghỉ', reasons: 'danh sách lý do nghỉ', employees: 'danh sách nhân viên' }
    const key = (...parts) => JSON.stringify([identityKey, ...parts])
    const jobs = [
      { id: 'records', key: key(listRangeStart, listRangeEnd), read: (options) => isApiConfigured
        ? veraApi.leaveRecords(listRangeStart, listRangeEnd, options)
        : loadLeaveRecords(listRangeStart, listRangeEnd).then((records) => ({ records })) },
      { id: 'daily', key: key(rangeStart, rangeEnd, statsEmployeeFilter), read: (options) => isApiConfigured
        ? veraApi.leaveDailyStats(rangeStart, rangeEnd, statsEmployeeFilter, options)
        : loadLeaveDailyStats(rangeStart, rangeEnd, statsEmployeeFilter).then((days) => ({ days })) },
      { id: 'reasons', key: key(date), read: (options) => isApiConfigured
        ? veraApi.leaveReasons(date, options)
        : loadLeaveReasons(date).then((names) => ({ reasons: names.map((name) => ({ name, requires_manual_penalty: false })) })) },
      { id: 'employees', key: key('employees'), read: (options) => isApiConfigured
        ? veraApi.employees(options)
        : loadEmployees().then((employees) => ({ employees })) },
    ]
    return pageLoader.current.run(jobs, {
      onlyChanged: options?.onlyChanged === true && !afterSave,
      onStart(ids) {
        setBusy(ids.length > 0)
        if (!afterSave) setError('')
        setLoadState((current) => ({ ...current, ...Object.fromEntries(ids.map((id) => [id, 'loading'])) }))
        if (ids.includes('reasons')) {
          recordReasonsRevision.current += 1
          recordReasonsRef.current = {}
          setRecordReasonsByDate({})
          setRecordReasonErrors({})
        }
      },
      onData(id, data) {
        // Publish each result immediately; a slow catalog must not hide records.
        if (id === 'daily') setDailyStats(data.days || [])
        if (id === 'records') {
          const loadedRecords = data.records || []
          setRecords(loadedRecords)
          setReasonDrafts(Object.fromEntries(loadedRecords.map((item) => [item.record_uid, item.leave_reason])))
          setSelectedUids([])
        }
        if (id === 'reasons') {
          setReasons(data.reasons || [])
          recordReasonsRef.current = { ...recordReasonsRef.current, [date]: data.reasons || [] }
          setRecordReasonsByDate(recordReasonsRef.current)
          if (isApiConfigured) {
            setEmployeeSelfServicePolicy({
              enabled: data.employee_self_service_policy?.enabled !== false,
              regular_notice_days: Number(data.employee_self_service_policy?.regular_notice_days ?? 3),
              unpaid_notice_days: Number(data.employee_self_service_policy?.unpaid_notice_days ?? 1),
            })
            setLetanLeavePolicy({
              enabled: data.letan_leave_policy?.enabled !== false,
              groups: (data.letan_leave_policy?.groups || []).map((group) => ({ ...group, reasons: [...(group.reasons || [])] })),
            })
          }
        }
        if (id === 'employees') setEmployees(data.employees || [])
        setLoadState((current) => ({ ...current, [id]: 'ready' }))
      },
      onError(id, err) {
        setLoadState((current) => ({ ...current, [id]: 'error' }))
        if (id === 'reasons') setRecordReasonErrors((current) => ({ ...current, [date]: err.message || 'Không tải được lý do nghỉ.' }))
        if (!afterSave) {
          setError((current) => [current, `Không tải được ${sources[id]}: ${err.message || 'Lỗi PostgreSQL/Supabase.'}`].filter(Boolean).join(' '))
        }
      },
      onFinish() { setBusy(false) },
    })
  }, [date, identityKey, listRangeEnd, listRangeStart, rangeEnd, rangeStart, statsEmployeeFilter])
  latestLoad.current = load

  useEffect(() => {
    const loader = pageLoader.current
    void load({ onlyChanged: true })
    return () => {
      loader.invalidate()
      recordReasonsRevision.current += 1
    }
  }, [load])

  const fetchRecordReasons = useCallback(async (recordDate, isActive = () => true) => {
    if (!recordDate || recordReasonsRef.current[recordDate] || pendingReasonDates.current.has(recordDate)) return
    pendingReasonDates.current.add(recordDate)
    const revision = recordReasonsRevision.current
    const currentRequest = () => isActive() && revision === recordReasonsRevision.current
    if (currentRequest()) setRecordReasonErrors((current) => ({ ...current, [recordDate]: '' }))
    try {
      const result = await veraApi.leaveReasons(recordDate)
      if (currentRequest()) {
        recordReasonsRef.current = { ...recordReasonsRef.current, [recordDate]: result.reasons || [] }
        setRecordReasonsByDate(recordReasonsRef.current)
      }
    } catch (err) {
      if (currentRequest()) setRecordReasonErrors((current) => ({ ...current, [recordDate]: err.message || 'Không tải được lý do nghỉ.' }))
    } finally {
      pendingReasonDates.current.delete(recordDate)
    }
  }, [])

  useEffect(() => {
    if (!isApiConfigured || busy || pageLoader.current.isLoading()) return undefined
    let active = true
    const editableDates = [...new Set(records
      .filter((item) => canEditLeaveRecord({
        role,
        allowedByPermission: canEdit,
        recordDate: item?.leave_date,
        currentReason: item?.leave_reason,
        currentLeaveType: item?.leave_type,
        today: today(),
        isOwnRecord: normalizeSearch(item?.employee_name) === normalizeSearch(user?.employee_username),
        employeeSelfServicePolicy,
        letanLeavePolicy,
      }))
      .map((item) => item.leave_date))]
      .filter((recordDate) => recordDate && recordDate !== date && !recordReasonsRef.current[recordDate])

    const loadEditableDateReasons = async () => {
      // One read per distinct date, sequentially for the VPS connection pool.
      // Publish each completed date immediately; never substitute another day.
      for (const recordDate of editableDates) {
        if (!active) break
        await fetchRecordReasons(recordDate, () => active)
      }
    }
    void loadEditableDateReasons()
    return () => { active = false }
  }, [busy, canEdit, date, employeeSelfServicePolicy, letanLeavePolicy, records, role, user?.employee_username, fetchRecordReasons])

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
  const changedRecords = records.filter((item) => (
    canEditRecord(item)
    && reasonDrafts[item.record_uid]
    && reasonDrafts[item.record_uid] !== item.leave_reason
  ))
  const canEditVisibleRecord = loadState.records === 'ready' && filteredRecords.some((item) => canEditRecord(item))
  const canDeleteVisibleRecord = loadState.records === 'ready' && filteredRecords.some((item) => canDeleteRecord(item))
  const deletableSelectedUids = selectedUids.filter((uid) => {
    const item = records.find((record) => record.record_uid === uid)
    return item && canDeleteRecord(item)
  })

  const reasonOptionsForRecord = (item) => {
    const catalog = isApiConfigured
      ? (recordReasonsByDate[item?.leave_date] || (item?.leave_date === date ? reasons : []))
      : reasons
    const group = letanReasonChoices(role, item?.leave_date, item?.leave_reason, today(), letanLeavePolicy)
    if (!group) return catalog.filter((reason) => canChangeLeaveReason(recordPermissionContext(item), reason))
    return group.map((name) => catalog.find((reason) => normalizeSearch(reason.name) === normalizeSearch(name)) || ({ name }))
  }

  const reasonValueForRecord = (item) => {
    if (reasonDrafts[item.record_uid]) return reasonDrafts[item.record_uid]
    const group = letanReasonChoices(role, item?.leave_date, item?.leave_reason, today(), letanLeavePolicy)
    if (!group) return item.leave_reason
    return group.find((reason) => normalizeSearch(reason) === normalizeSearch(item.leave_reason)) || group[2]
  }

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

  const toggleSelected = (item) => {
    if (!canDeleteRecord(item)) return
    const recordUid = item.record_uid
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
    if (mutationRef.current || changedRecords.length === 0) return
    mutationRef.current = true
    const updatedCount = changedRecords.length
    setManaging(true)
    setListActionNotice(null)
    try {
      for (const item of changedRecords) {
        const nextReason = reasonOptionsForRecord(item).find((reason) => reason.name === reasonDrafts[item.record_uid])
        if (!nextReason) throw new Error(`Lý do nghỉ đã chọn không còn được phép cho ${shortEmployeeName(item.employee_name)} ngày ${formatDateDisplay(item.leave_date)}. Hãy tải lại danh sách.`)
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
      const refreshed = await latestLoad.current({ afterSave: true })
      if (!refreshed) {
        setWarnings((current) => [
          ...current,
          'Lịch nghỉ đã được lưu. Dữ liệu màn hình chưa tải lại được; không bấm Ghi lần nữa, hãy bấm Làm mới.',
        ])
      }
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
      mutationRef.current = false
      setManaging(false)
    }
  }
  useAutoSave({ signature: JSON.stringify(changedRecords.map((item) => [item.record_uid, reasonDrafts[item.record_uid]])), enabled: !busy && !managing && !saving && changedRecords.length > 0, save: saveEdits, rootRef: leavePageRef, lockRef: mutationRef })

  const deleteSelected = async () => {
    if (deletableSelectedUids.length === 0) return
    if (!window.confirm(`Xóa ${deletableSelectedUids.length} lịch nghỉ đã chọn?`)) return
    const deletedCount = deletableSelectedUids.length
    setManaging(true)
    setListActionNotice(null)
    try {
      await veraApi.deleteLeaves(deletableSelectedUids)
      await latestLoad.current({ afterSave: true })
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

  const chooseRangeFilter = (filter) => {
    setRangeFilter(filter)
    if (filter === 'Tùy chỉnh') return
    const [start, end] = rangeForFilter(filter)
    setRangeStart(start)
    setRangeEnd(end)
    setDate(filter === 'Hôm nay' || filter === 'Tháng này' || filter === 'Tuần này' ? today() : start)
  }

  const changeCustomStart = (value) => {
    if (!value) return
    setRangeStart(value)
    if (value > rangeEnd) setRangeEnd(value)
    setDate(value)
  }

  const changeCustomEnd = (value) => {
    if (!value) return
    if (value.slice(0, 7) !== activeMonth) setDate(value)
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
    if (start.slice(0, 7) !== activeMonth) setDate(start)
    setListRangeStart(start)
    setListRangeEnd(end)
  }

  const changeListCustomStart = (value) => {
    if (!value) return
    setSelectedUids([])
    if (value.slice(0, 7) !== activeMonth) setDate(value)
    setListRangeStart(value)
    if (value > listRangeEnd) setListRangeEnd(value)
  }

  const changeListCustomEnd = (value) => {
    if (!value) return
    setSelectedUids([])
    if (value.slice(0, 7) !== activeMonth) setDate(value)
    setListRangeEnd(value)
    if (value < listRangeStart) setListRangeStart(value)
  }

  const selectViewedDate = (value) => {
    if (!value) return
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
    event?.preventDefault()
    if (mutationRef.current || !leaveFormRef.current?.checkValidity()) return
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
    mutationRef.current = true
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
      const refreshed = await latestLoad.current({ afterSave: true })
      if (!refreshed) {
        setWarnings((current) => [...current, 'Lịch nghỉ đã được lưu, nhưng chưa thể làm mới dữ liệu hiển thị. Vui lòng bấm Làm mới; không cần ghi lại lịch nghỉ.'])
      }
      await refreshWatchDates()
    } catch (err) {
      setError(`KHÔNG THÀNH CÔNG (${err.message || 'Không ghi được lịch nghỉ.'})`)
    } finally {
      mutationRef.current = false
      setSaving(false)
    }
  }
  useAutoSave({ signature: JSON.stringify([date, form]), enabled: canCreate && !busy && !saving && !managing && Boolean(form.employee_name && form.leave_reason) && (!selectedReason?.requires_manual_penalty || form.manual_penalty !== ''), save: submit, rootRef: leaveFormRef, lockRef: mutationRef, waitForExit: true })

  return (
    <div ref={leavePageRef}>
      <div data-ui-key="u-2f745fc2db4b" className="page-heading-row">
        <div><h1 className="page-title">Đăng ký nghỉ</h1></div>
        <button data-ui-key="u-a75ced431985" data-ui-label-default="Làm mới" className="secondary-button" onClick={load} disabled={busy}><RefreshCw size={17} className={busy ? 'spin' : ''} /><UiCustomText uiKey="u-a75ced431985"> Làm mới</UiCustomText></button>
      </div>

      {!isApiConfigured && (
        <div className="warning-box"><strong>Chế độ chỉ đọc.</strong> API chưa được cấu hình nên nút Ghi đang khóa an toàn.</div>
      )}

      {isApiConfigured && user?.registration_locked && (
        <div className="warning-box"><strong>Đang khóa đăng ký.</strong> Admin đang tạm khóa quyền đăng ký nghỉ của vai trò {role}.</div>
      )}

      {isApiConfigured && user?.permissions?.leave_create === false && !employeeSelfService && (
        <div className="warning-box"><strong>Chế độ chỉ xem.</strong> Tài khoản này chưa được cấp quyền ghi lịch nghỉ.</div>
      )}

      <UiToolbar data-ui-key="u-03cf771004d1" className="date-toolbar viewed-date-toolbar">
        <DatePickerControl
          label="Ngày đang xem"
          value={date}
          onChange={selectViewedDate}
          max={role === 'admin' ? undefined : maxEmployeeDate}
        />
        <button data-ui-key="u-97e97b7f1418"
          type="button"
          className={`watch-current-date-button ${watchedDateSet.has(date) ? 'active' : ''} ${unreadWatchDateSet.has(date) ? 'ringing' : ''}`}
          onClick={() => toggleWatchDate(date)}
          disabled={!isApiConfigured || Boolean(watchBusyDate)}
          aria-pressed={watchedDateSet.has(date)}
        >
          {watchedDateSet.has(date) ? <BellRing size={17} /> : <Bell size={17} />}
          {watchedDateSet.has(date) ? 'Đang quan tâm ngày này' : 'Quan tâm ngày này'}
        </button>
        <button data-ui-key="u-a1afda5e3fbc"
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
      </UiToolbar>

      {pushMessage && <div className="success-box push-status-box">{pushMessage}</div>}

      {unreadWatchDates.length > 0 && (
        <section data-ui-key="u-32fb4b567164" className="watch-notification-panel ringing" role="alert" aria-live="assertive">
          <div data-ui-key="u-5fb72f06c361" className="watch-notification-heading">
            <button data-ui-key="u-0720dc449144" type="button" className="watch-ringing-button" onClick={ringWatchBell} aria-label="Phát lại chuông thông báo">
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
                <button data-ui-key="u-f2d195b0f735" data-ui-label-default="Đã xem" type="button" onClick={() => acknowledgeWatchDate(item.date)} disabled={watchBusyDate === item.date}><UiCustomText uiKey="u-f2d195b0f735">
                  Đã xem
                </UiCustomText></button>
              </div>
            ))}
          </div>
        </section>
      )}

      {watchError && <div className="error-box watch-error-box">{watchError}</div>}

      <div className="content-grid">
        <section data-ui-key="u-3ad934e889f0" className="panel registration-panel">
          <div data-ui-key="u-d92c5005f472" className="panel-title-row">
            <div><h2>ĐĂNG KÝ MỚI</h2></div>
          </div>
          {employeeSelfService && (
            <div className="info-box">
              Nhân viên được đăng ký, sửa và xóa lịch của chính mình trước ít nhất {employeeSelfServicePolicy.regular_notice_days} ngày;
              riêng Loại nghỉ Không phép trước ít nhất {employeeSelfServicePolicy.unpaid_notice_days} ngày.
            </div>
          )}
          <form ref={leaveFormRef} className="leave-form" onSubmit={submit}>
            <fieldset disabled={saving || managing} className="autosave-fields">
            <label>Tên nhân viên</label>
            <select
              value={form.employee_name}
              onChange={(e) => setForm((current) => ({ ...current, employee_name: e.target.value }))}
              disabled={!canChooseEmployee || loadState.employees !== 'ready'}
              required
            >
              <option value="">{loadState.employees === 'loading' ? 'Đang tải nhân viên…' : loadState.employees === 'error' ? 'Chưa tải được nhân viên' : '-- Chọn nhân viên --'}</option>
              {registrationEmployees.map((employee) => (
                <option key={employee.username} value={employee.username}>
                  {shortEmployeeName(employee.username)}
                </option>
              ))}
            </select>

            <label>Lý do nghỉ</label>
            <select
              value={form.leave_reason}
              disabled={loadState.reasons !== 'ready'}
              onChange={(e) => {
                const leaveReason = e.target.value
                setForm((current) => ({ ...current, leave_reason: leaveReason, manual_penalty: '' }))
              }}
              required
            >
              <option value="">{loadState.reasons === 'loading' ? 'Đang tải lý do nghỉ…' : loadState.reasons === 'error' ? 'Chưa tải được lý do nghỉ' : '-- Chọn lý do nghỉ --'}</option>
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
            <button data-ui-key="u-7712757bd8c0" className="primary-button" type="submit" disabled={saving || !canCreate}>{saving ? 'Đang kiểm tra & ghi…' : 'Ghi'}</button>
            </fieldset>
          </form>
        </section>

        <section data-ui-key="u-1da4ebbbf42b" className="panel daily-summary-panel">
          <div data-ui-key="u-18eec50740be" className="panel-title-row">
            <div>
              <h2>THỐNG KÊ</h2>
            </div>
            <UiToolbar data-ui-key="u-e85272e9d623" className="list-actions statistics-title-actions">
              {canViewPenalty && <div className="penalty-chip">Tổng tiền phạt: {loadState.daily === 'ready' ? `${statsTotalPenalty.toLocaleString('vi-VN')}đ` : '…'}</div>}
              <button data-ui-key="u-7f2d0324788b" data-ui-label-default="Làm mới" type="button" className="secondary-button compact" onClick={load} disabled={busy}>
                <RefreshCw size={15} className={busy ? 'spin' : ''} /><UiCustomText uiKey="u-7f2d0324788b"> Làm mới
              </UiCustomText></button>
            </UiToolbar>
          </div>
          <UiToolbar data-ui-key="u-3f286760a70f" className="list-filter-toolbar statistics-filter-toolbar">
            <div className="range-filter-buttons list-range-buttons" role="group" aria-label="Lọc thời gian thống kê">
              {STAT_DATE_FILTERS.map((filter) => (
                <button data-ui-key="u-9b43d234f8b2"
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
                <ClearableSearchInput
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
              <UiToolbar data-ui-key="u-9aba1185d8a1" className="statistics-search-actions">
                <button data-ui-key="u-f2d17432d990" data-ui-label-default="Tìm" type="button" className="secondary-button compact" onClick={() => setStatsEmployeeFilter(statsEmployeeSearch.trim())} disabled={busy}>
                  <Search size={14} /><UiCustomText uiKey="u-f2d17432d990"> Tìm
                </UiCustomText></button>
                {(statsEmployeeFilter || statsEmployeeSearch) && (
                  <button data-ui-key="u-75e16b4be615" data-ui-label-default="Bỏ lọc"
                    type="button"
                    className="secondary-button compact"
                    onClick={() => {
                      setStatsEmployeeSearch('')
                      setStatsEmployeeFilter('')
                    }}
                    disabled={busy}
                  >
                    <X size={14} /><UiCustomText uiKey="u-75e16b4be615"> Bỏ lọc
                  </UiCustomText></button>
                )}
              </UiToolbar>
            </div>
          </UiToolbar>
          <div className="table-wrap daily-summary-wrap" aria-busy={loadState.daily === 'loading'}>
            <table data-ui-key="u-dc5f9cd8d11f" className={`daily-summary-table ${canViewPenalty ? 'with-penalty' : 'without-penalty'}`}>
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
                  <th data-ui-key="u-acb18b777955" data-ui-label-default="Ngày"><UiCustomText uiKey="u-acb18b777955">Ngày</UiCustomText></th>
                  <th data-ui-key="u-5065da3b81fb"><span className="full-column-label">Thứ ngày</span><span className="compact-column-label">Thứ</span></th>
                  <th data-ui-key="u-f5d227449098" className="center"><span className="full-column-label">Tổng nghỉ</span><span className="compact-column-label">Nghỉ</span></th>
                  <th data-ui-key="u-52511d1d3ecc" className="center"><span className="full-column-label">✅ Có phép</span><span className="compact-column-label">Phép</span></th>
                  <th data-ui-key="u-41df05a165db" className="center"><span className="full-column-label">⚠️ Phát sinh</span><span className="compact-column-label">PS</span></th>
                  <th data-ui-key="u-19a64ea770bf" className="center"><span className="full-column-label">❌ Không phép</span><span className="compact-column-label">K.phép</span></th>
                  {canViewPenalty && <th data-ui-key="u-ab9266c56a98" className="right"><span className="full-column-label">💰 Tổng tiền phạt</span><span className="compact-column-label">Phạt</span></th>}
                </tr>
              </thead>
              <tbody>
                {loadState.daily !== 'ready' ? (
                  <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell" role="status">{loadState.daily === 'loading' ? 'Đang tải thống kê lịch nghỉ…' : 'Chưa tải được thống kê. Vui lòng bấm Làm mới.'}</td></tr>
                ) : dailyStats.length === 0 ? (
                  <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell">{statsEmployeeFilter ? `Không có dữ liệu của ${statsEmployeeFilter} trong khoảng thời gian này.` : 'Không có dữ liệu trong khoảng thời gian này.'}</td></tr>
                ) : dailyStats.map((day) => (
                  <tr key={day.date} className={day.date === date ? 'selected-day-row' : ''}>
                    <td>
                      <UiToolbar data-ui-key="u-1902657b4ec3" className="daily-date-actions">
                        <button data-ui-key="u-f648a7666974" type="button" className="date-link" onClick={() => selectViewedDate(day.date)}>
                          {formatDateDisplay(day.date)}
                        </button>
                        <button data-ui-key="u-0d08896737af"
                          type="button"
                          className={`watch-date-icon ${watchedDateSet.has(day.date) ? 'active' : ''} ${unreadWatchDateSet.has(day.date) ? 'ringing' : ''}`}
                          onClick={() => toggleWatchDate(day.date)}
                          disabled={Boolean(watchBusyDate)}
                          aria-label={watchedDateSet.has(day.date) ? `Bỏ quan tâm ngày ${formatDateDisplay(day.date)}` : `Quan tâm ngày ${formatDateDisplay(day.date)}`}
                          aria-pressed={watchedDateSet.has(day.date)}
                        >
                          {watchedDateSet.has(day.date) ? <BellRing size={14} /> : <Bell size={14} />}
                        </button>
                      </UiToolbar>
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

        <section data-ui-key="u-6a4d9baaa43d" className="panel leave-list-panel"
          data-leave-start={listRangeStart} data-leave-end={listRangeEnd} data-leave-employee={employeeSearch}>
          <div data-ui-key="u-8b2d8ad1d8f1" className="panel-title-row">
            <div>
              <h2>DANH SÁCH</h2>
            </div>
            <button data-ui-key="u-4c4154cfd167" data-ui-label-default="Làm mới" type="button" className="secondary-button compact" onClick={load} disabled={busy}>
              <RefreshCw size={15} className={busy ? 'spin' : ''} /><UiCustomText uiKey="u-4c4154cfd167"> Làm mới
            </UiCustomText></button>
          </div>
          <UiToolbar data-ui-key="u-673fd5d1a86a" className="list-actions">
              {role === 'admin' && <button data-ui-key="u-ac98242f10d4" type="button" className="secondary-button compact export-button" onClick={exportExcel} disabled={exporting}><Download size={15} /> {exporting ? 'Đang xuất…' : 'Export to Excel'}</button>}
              {canEditVisibleRecord && <button data-ui-key="u-1ce6547689e1" data-ui-label-default="Lưu sửa" type="button" className="secondary-button compact" onClick={saveEdits} disabled={managing || changedRecords.length === 0}><Save size={15} /><UiCustomText uiKey="u-1ce6547689e1"> Lưu sửa</UiCustomText></button>}
              {canDeleteVisibleRecord && <button data-ui-key="u-dad1744abe2f" data-ui-label-default="Xóa đã chọn" type="button" className="danger-button compact" onClick={deleteSelected} disabled={managing || deletableSelectedUids.length === 0}><Trash2 size={15} /><UiCustomText uiKey="u-dad1744abe2f"> Xóa đã chọn</UiCustomText></button>}
              {canViewPenalty && <div className="penalty-chip">Phạt: {loadState.records === 'ready' ? `${totalPenalty.toLocaleString('vi-VN')}đ` : '…'}</div>}
          </UiToolbar>
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
              <button data-ui-key="u-3ea62cdcdeb4" type="button" className="list-action-notice-close" onClick={() => setListActionNotice(null)} aria-label="Đóng thông báo">
                <X size={15} />
              </button>
            </div>
          )}
          <UiToolbar data-ui-key="u-1bf317df3f46" className="list-filter-toolbar">
            <div className="range-filter-buttons list-range-buttons" role="group" aria-label="Lọc thời gian danh sách">
              {LIST_DATE_FILTERS.map((filter) => (
                <button data-ui-key="u-0512fe10d2e8"
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
              <ClearableSearchInput
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
          </UiToolbar>
          <div className="table-wrap leave-list-wrap" aria-busy={loadState.records === 'loading'}>
            <table data-ui-key="u-1d60b99a3b6d" className={`leave-records-table ${canViewPenalty ? 'with-penalty' : 'without-penalty'}`}>
              <colgroup>
                <col className="leave-col-select" />
                <col className="leave-col-date" />
                <col className="leave-col-weekday" />
                <col className="leave-col-employee" />
                <col className="leave-col-reason" />
                <col className="leave-col-detail" />
                {canViewPenalty && <col className="leave-col-penalty" />}
              </colgroup>
              <thead><tr><th data-ui-key="u-3f090c8da00d" data-ui-label-default="Chọn" className="select-column"><UiCustomText uiKey="u-3f090c8da00d">Chọn</UiCustomText></th><th data-ui-key="u-06ade8ca026c" data-ui-label-default="Ngày"><UiCustomText uiKey="u-06ade8ca026c">Ngày</UiCustomText></th><th data-ui-key="u-e58316817ea9" data-ui-label-default="Thứ"><UiCustomText uiKey="u-e58316817ea9">Thứ</UiCustomText></th><th data-ui-key="u-cf02e7475dd8" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-cf02e7475dd8">Nhân viên</UiCustomText></th><th data-ui-key="u-a8a96dc68700" data-ui-label-default="Lý do"><UiCustomText uiKey="u-a8a96dc68700">Lý do</UiCustomText></th><th data-ui-key="u-802a8e189292" data-ui-label-default="Chi tiết"><UiCustomText uiKey="u-802a8e189292">Chi tiết</UiCustomText></th>{canViewPenalty && <th data-ui-key="u-5034577af92e" data-ui-label-default="Phạt" className="right"><UiCustomText uiKey="u-5034577af92e">Phạt</UiCustomText></th>}</tr></thead>
              <tbody>
                {loadState.records !== 'ready' ? (
                  <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell" role="status">{loadState.records === 'loading' ? 'Đang tải danh sách lịch nghỉ…' : 'Chưa tải được danh sách. Vui lòng bấm Làm mới.'}</td></tr>
                ) : filteredRecords.length === 0 ? (
                  <tr><td colSpan={canViewPenalty ? 7 : 6} className="empty-cell">Không có lịch nghỉ phù hợp bộ lọc.</td></tr>
                ) : filteredRecords.map((item) => (
                  <tr key={item.record_uid || `${item.employee_name}-${item.leave_reason}`}>
                    <td className="select-column"><input type="checkbox" aria-label={`Chọn lịch của ${shortEmployeeName(item.employee_name)}`} checked={canDeleteRecord(item) && selectedUids.includes(item.record_uid)} onChange={() => toggleSelected(item)} disabled={!canDeleteRecord(item) || managing} /></td>
                    <td><button data-ui-key="u-32bb2e0b8700" type="button" className="date-link list-date-link" onClick={() => selectViewedDate(item.leave_date)}>{formatDateDisplay(item.leave_date)}</button></td>
                    <td className="weekday-cell">{item.weekday_label || weekdayForDate(item.leave_date)}</td>
                    <td><strong>{shortEmployeeName(item.employee_name)}</strong></td>
                    <td className="reason-edit-cell">
                      {canEditRecord(item) ? (
                        <select aria-label={`Sửa lý do nghỉ của ${shortEmployeeName(item.employee_name)} ngày ${formatDateDisplay(item.leave_date)}`} value={reasonValueForRecord(item)} onFocus={() => { if (!recordReasonsByDate[item.leave_date] && !letanReasonChoices(role, item.leave_date, item.leave_reason, today(), letanLeavePolicy)) void fetchRecordReasons(item.leave_date) }} onChange={(event) => setReasonDrafts((current) => ({ ...current, [item.record_uid]: event.target.value }))} disabled={managing || !isApiConfigured || (!recordReasonsByDate[item.leave_date] && !letanReasonChoices(role, item.leave_date, item.leave_reason, today(), letanLeavePolicy))}>
                          {!letanReasonChoices(role, item.leave_date, item.leave_reason, today(), letanLeavePolicy) && !reasonOptionsForRecord(item).some((reason) => reason.name === item.leave_reason) && <option value={item.leave_reason}>{item.leave_reason}</option>}
                          {reasonOptionsForRecord(item).map((reason) => <option key={reason.name} value={reason.name}>{reason.name}</option>)}
                        </select>
                      ) : <span>{item.leave_reason}</span>}
                      {canEditRecord(item) && isApiConfigured && !recordReasonsByDate[item.leave_date] && !letanReasonChoices(role, item.leave_date, item.leave_reason, today(), letanLeavePolicy) && (
                        recordReasonErrors[item.leave_date]
                          ? <div role="alert"><small>{recordReasonErrors[item.leave_date]}</small><button data-ui-key="u-26f8c2b95ba3" data-ui-label-default="Thử tải lại lý do" type="button" className="text-button" disabled={managing} onClick={() => fetchRecordReasons(item.leave_date)}><UiCustomText uiKey="u-26f8c2b95ba3">Thử tải lại lý do</UiCustomText></button></div>
                          : <small role="status">Đang tải lý do nghỉ cho ngày {formatDateDisplay(item.leave_date)}…</small>
                      )}
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
      <VeraDateInput
        aria-label={label}
        value={value}
        min={min}
        max={max}
        onChange={(event) => onChange(event.target.value)}
      />
    </div>
  )
}
