import { showSystemDialog } from '../lib/systemDialogs'
import LiveTourSearchSelect from '../components/LiveTourSearchSelect'
import PayrollHistorySearch from '../components/PayrollHistorySearch'
import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { formatVeraDate, formatVeraDateTime } from '../lib/veraDate'
import { searchTextMatches } from '../lib/searchText'
import { Banknote, CalendarDays, CheckCircle2, Download, History, Mail, Plus, RefreshCw, Save, Search, Share2, Send, Settings2, Trash2 } from 'lucide-react'
import { useEffect, useLayoutEffect, useRef, useState } from 'react'
import { apiRequest, apiBinaryResponse } from '../lib/api'
import useFitPayrollTables from '../lib/useFitPayrollTables'
import VeraMoneyInput from '../components/VeraMoneyInput'
import { createPayrollOperationScope, hasPayrollRevisions, hasPendingPayrollEvidence, normalizeSalaryConfigTables, PAYROLL_BACKEND_UPDATE_REQUIRED, payrollPendingLabel, recalculateDepartmentPayroll as recalculate, salarySource, salarySourceLabel, supportsPayrollContract, versionedPayrollPath } from '../lib/departmentPayrollSource'
import './DepartmentPayrollPanel.css'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const monthNow = () => {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit' }).formatToParts(new Date())
  return `${parts.find(part => part.type === 'year').value}-${parts.find(part => part.type === 'month').value}`
}
const displayIsoDate = value => formatVeraDate(value)
const normalizeSearch = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replaceAll('đ', 'd').toLowerCase().trim()

async function request(path, options = {}) {
  options.signal?.throwIfAborted()
  if (options.download) {
    const blob = await (await apiBinaryResponse(path, options)).blob()
    options.signal?.throwIfAborted()
    return blob
  }
  if (!path.includes('/combined/draft')) return apiRequest(path, options)
  const controller = new AbortController()
  const abort = () => controller.abort()
  options.signal?.addEventListener('abort', abort, { once: true })
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; controller.abort() }, 30000)
  try { return await apiRequest(path, { ...options, signal: controller.signal }) }
  catch (error) {
    options.signal?.throwIfAborted()
    if (timedOut) throw new Error(['PUT', 'DELETE'].includes(options.method)
      ? 'Máy chủ phản hồi quá lâu. Chưa xác nhận được kết quả thao tác; hãy Mở bảng nháp để kiểm tra trước khi lưu lại.'
      : 'Máy chủ phản hồi quá lâu khi mở bảng nháp. Vui lòng thử lại.')
    throw error
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}

const editableFields = [
  ['base_salary', 'Lương cơ bản'], ['full_allowance', 'Phụ cấp Full'],
  ['attendance_bonus', 'Chuyên cần'], ['responsibility', 'Trách nhiệm'],
  ['seniority', 'Thâm niên'], ['combo_sales', 'Bán combo'],
  ['advance', 'Ứng lương'], ['violation_penalty', 'Phạt vi phạm'], ['late_penalty', 'Phạt đi trễ'],
]

const operationsEmployeeFields = [
  ['rate_ca1', 'Lương giờ Ca 1'], ['rate_ca2_before_22', 'Ca 2 trước 22h'],
  ['rate_ca2_after_22', 'Ca 2 sau 22h'], ['full_day_allowance', 'Phụ cấp Full/ngày'],
  ['default_attendance_bonus', 'Chuyên cần'], ['default_responsibility', 'Trách nhiệm'],
  ['default_seniority', 'Thâm niên'], ['default_combo_sales', 'Bán combo'],
]

const tapvuEmployeeFields = [
  ['default_base_salary', 'Lương cơ bản/tháng'], ['default_attendance_bonus', 'Chuyên cần'],
  ['default_responsibility', 'Trách nhiệm'], ['default_seniority', 'Thâm niên'],
  ['default_combo_sales', 'Khoản cộng mặc định'],
]

export default function DepartmentPayrollPanel({ user, settingsOnly = false }) {
  // Never keep another account's payroll, prepared files or pending approvals.
  const identity = JSON.stringify([user?.id, user?.user_id, user?.employee_username, user?.username, user?.email, user?.role,
    Object.entries(user?.permissions || {}).sort(([a], [b]) => a.localeCompare(b)), settingsOnly])
  const mutationRef = useRef(null)
  const [mutation, setMutation] = useState(null)
  const updateMutation = value => { mutationRef.current = value; setMutation(value) }
  return <PayrollPanel key={identity} user={user} identity={identity} settingsOnly={settingsOnly} mutation={mutation} mutationRef={mutationRef} updateMutation={updateMutation} />
}

function PayrollPanel({ user, identity, settingsOnly, mutation, mutationRef, updateMutation }) {
  usePageRefresh(() => loadSettings(), () => Boolean(busy || (settingsBaseline && JSON.stringify([settings, salaryConfigTables, employeeCatalog]) !== settingsBaseline)))
  const pageRef = useRef(null)
  const hourlyRef = useRef(null)
  useFitPayrollTables(pageRef)
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const permissions = user?.permissions || {}
  const [backendCompatible, setBackendCompatible] = useState(null)
  const backendReady = backendCompatible === true
  const canConfig = isAdmin && (permissions.payroll_config_edit !== false)
  const canCalculate = isAdmin || Boolean(permissions.payroll_calculate)
  const canSave = isAdmin || permissions.payroll_save
  const canExport = isAdmin || permissions.payroll_export
  const canEmail = isAdmin || permissions.payroll_email
  const [month, setMonth] = useState(monthNow())
  const [settings, setSettings] = useState({})
  const [settingsBaseline, setSettingsBaseline] = useState('')
  const [employeeConfigRevision, setEmployeeConfigRevision] = useState(null)
  const [numericConfigDirty, setNumericConfigDirty] = useState(false)
  const [salaryConfigTables, setSalaryConfigTables] = useState({ operations: [], tapvu: [] })
  const [employeeCatalog, setEmployeeCatalog] = useState([])
  const [sourceSearch, setSourceSearch] = useState('')
  const [addDepartment, setAddDepartment] = useState('quanly')
  const [employeeSearch, setEmployeeSearch] = useState({ operations: '', tapvu: '' })
  const [pendingEmployee, setPendingEmployee] = useState({ operations: '', tapvu: '' })
  const [rows, setRows] = useState([])
  const [rowsMonth, setRowsMonth] = useState(null)
  const [draftRevision, setDraftRevision] = useState(null)
  const [historyRevision, setHistoryRevision] = useState(null)
  const operationScope = useRef(null)
  if (!operationScope.current) operationScope.current = createPayrollOperationScope()
  useLayoutEffect(() => {
    const scope = operationScope.current
    scope.mount()
    return () => scope.dispose()
  }, [])
  const [payrollSearch, setPayrollSearch] = useState('')
  const [departmentFilter, setDepartmentFilter] = useState('')
  const [history, setHistory] = useState([])
  const [historyOpen, setHistoryOpen] = useState(false)
  const [editingHistoryId, setEditingHistoryId] = useState('')
  const [calculationPeriod, setCalculationPeriod] = useState(null)
  const [selected, setSelected] = useState([])
  const [busyState, setBusy] = useState('')
  const mutationPending = mutation?.status === 'pending'
  const busy = busyState || (mutationPending ? mutation.key : '')
  const mutationUncertain = mutation?.status === 'uncertain' && (mutation.resource === 'settings' ? settingsOnly : mutation.month === month)
  const writeBlocked = !backendReady || mutationPending || mutationUncertain
  const [shareOpen, setShareOpen] = useState(false)
  const shareDialog = useRef(null)
  useEffect(() => {
    if (shareOpen && !shareDialog.current?.open) shareDialog.current?.showModal()
    if (!shareOpen) shareDialog.current?.close()
  }, [shareOpen])
  const [shareFiles, setShareFiles] = useState(null)
  const [notice, setNotice] = useState(null)

  useEffect(() => {
    const apply = (event) => {
      if (!backendReady || event.detail?.month !== month) return
      const totals = event.detail.byEmployee || {}
      if (!rows.some(row => Number(row.advance || 0) !== Number(totals[row.employee_username]?.payroll_total || 0))) return
      invalidateSnapshot()
      setRows(items => {
        let changed = false
        const next = items.map(row => {
          const advance = Number(totals[row.employee_username]?.payroll_total || 0)
          if (Number(row.advance || 0) === advance) return row
          changed = true
          return recalculate({ ...row, advance }, row.calculation_config || settings[row.department]?.config || {})
        })
        return changed ? next : items
      })
    }
    window.addEventListener('vera-salary-advance-summary', apply)
    return () => window.removeEventListener('vera-salary-advance-summary', apply)
  }, [month, settings, rows, backendReady])

  const visibleRows = rows.filter(row => (!departmentFilter || row.department === departmentFilter)
    && searchTextMatches([row.employee_name, row.employee_username], payrollSearch))
  const rowDepartments = [...new Map(rows.map(row => [row.department, row.department_label])).entries()]
  const totalNet = visibleRows.reduce((sum, row) => sum + Number(row.net_salary || 0), 0)
  const totalAdvance = visibleRows.reduce((sum, row) => sum + Number(row.advance || 0), 0)

  const pendingEvidence = hasPendingPayrollEvidence(rows)
  const visiblePendingEvidence = hasPendingPayrollEvidence(visibleRows)
  const selectedPendingEvidence = hasPendingPayrollEvidence(rows.filter(row => selected.includes(row.employee_username)))
  const invalidateSnapshot = () => {
    operationScope.current.invalidate()
    setBusy(''); setShareOpen(false); setShareFiles(null)
  }
  const clearPayroll = () => {
    setRows([]); setRowsMonth(null); setDraftRevision(null); setHistoryRevision(null); setSelected([]); setEditingHistoryId(''); setCalculationPeriod(null)
    setPayrollSearch(''); setDepartmentFilter('')
  }
  const changeMonth = value => {
    if (value === month || mutationRef.current?.status === 'pending') return
    invalidateSnapshot(); clearPayroll(); setNotice(null); setMonth(value)
  }
  const changeSearch = value => { if (mutationRef.current?.status === 'pending') return; invalidateSnapshot(); setPayrollSearch(value); setSelected([]) }
  const changeDepartment = value => { if (mutationRef.current?.status === 'pending') return; invalidateSnapshot(); setDepartmentFilter(value); setSelected([]) }

  const resolveUncertain = (resource, targetMonth = month) => {
    const current = mutationRef.current
    if (current?.status === 'uncertain' && current.resource === resource
      && (resource === 'settings' || current.month === targetMonth)) updateMutation(null)
  }
  useEffect(() => {
    if (mutation?.status !== 'settled' || mutation.identity !== identity || !mutation.stale) return
    if (mutation.resource === 'payroll' && mutation.month === month && rowsMonth === month) {
      if (mutation.result?.draft_revision != null) setDraftRevision(mutation.result.draft_revision)
      if (mutation.result?.history_revision != null) setHistoryRevision(mutation.result.history_revision)
      setNotice({ type: 'success', message: 'Máy chủ đã xác nhận thao tác lưu trước. Những thay đổi mới hơn trên màn hình chưa được lưu.' })
    }
  }, [mutation, identity, month, rowsMonth])

  const run = async (key, callback) => {
    const task = operationScope.current.start()
    task.request = async (path, options = {}) => {
      task.assertCurrent()
      const { mutationMonth = month, ...transport } = options
      const discovery = path === '/v2/department-payroll/settings' && !transport.method
      const useVersioned = !discovery && (backendReady || transport.method || transport.download || path.includes('/calculate'))
      const requestPath = useVersioned ? versionedPayrollPath(path) : path
      const performRequest = async requestOptions => {
        try { return await request(requestPath, requestOptions) }
        catch (error) {
          if (useVersioned && [404, 405].includes(error.status)) {
            setBackendCompatible(false)
            error.message = PAYROLL_BACKEND_UPDATE_REQUIRED
          }
          throw error
        }
      }
      const isMutation = ['PUT', 'DELETE'].includes(transport.method)
        || (transport.method === 'POST' && /\/(complete|open|email)(?:\?|$)/.test(path))
      let result
      if (isMutation) {
        const resource = path.includes('/settings') ? 'settings' : 'payroll'
        const outstanding = mutationRef.current
        if (outstanding?.status === 'pending') throw new Error('Thao tác lưu trước vẫn đang chờ máy chủ xác nhận. Vui lòng chờ kết quả.')
        if (outstanding?.status === 'uncertain' && outstanding.resource === resource
          && (resource === 'settings' || outstanding.month === mutationMonth)) throw new Error('Chưa xác nhận kết quả thao tác trước. Hãy làm mới cấu hình hoặc Mở bảng nháp để kiểm tra trước khi lưu lại.')
        const write = { status: 'pending', key, resource, month: mutationMonth, identity }
        updateMutation(write)
        try {
          // Aborting a browser request cannot roll back a committed mutation.
          // Keep its settlement barrier across view/account/permission changes.
          result = await performRequest(transport)
          updateMutation({ ...write, status: 'settled', result, stale: !task.isCurrent() })
        } catch (error) {
          const uncertain = !error.status || error.status >= 500 || error.status === 409
          updateMutation(uncertain ? { ...write, status: 'uncertain', conflict: error.status === 409 } : null)
          throw error
        }
      } else {
        result = await performRequest({ ...transport, signal: task.signal })
      }
      task.assertCurrent()
      return result
    }
    task.confirm = async message => {
      task.assertCurrent()
      const dialog = showSystemDialog({ message, kind: 'confirm' })
      const close = () => dialog.close(false)
      task.signal.addEventListener('abort', close, { once: true })
      try {
        const accepted = await dialog.result
        task.assertCurrent()
        return accepted
      } finally { task.signal.removeEventListener('abort', close) }
    }
    setBusy(key); setNotice(null); setShareFiles(null)
    if (key !== 'share-prepare') setShareOpen(false)
    try { await callback(task) }
    catch (error) { if (task.isCurrent() && error.name !== 'AbortError') setNotice({ type: 'error', message: error.message }) }
    finally { if (task.isCurrent()) setBusy('') }
  }

  const loadSettings = async () => run('settings-load', async task => {
    const [result, historyResult] = await Promise.all([
      task.request('/v2/department-payroll/settings'),
      settingsOnly ? Promise.resolve({ items: [] }) : task.request('/v2/department-payroll/combined/history'),
    ])
    task.assertCurrent()
    setBackendCompatible(supportsPayrollContract(result))
    const tables = normalizeSalaryConfigTables(result.salary_config_tables)
    const catalog = (result.salary_employee_catalog || []).map(row => ({ ...row, salary_source: salarySource(row.salary_source) }))
    setSettings(result.departments || {})
    setSettingsBaseline(JSON.stringify([result.departments || {}, tables, catalog]))
    setEmployeeConfigRevision(result.employee_config_revision ?? null)
    resolveUncertain('settings')
    setAddDepartment(Object.keys(result.departments || {}).find(key => result.departments[key].config?.calculation_mode === 'hourly') || '')
    setSalaryConfigTables(tables); setNumericConfigDirty(false)
    setEmployeeCatalog(catalog)
    setHistory(historyResult.items || [])
  })

  useEffect(() => { void loadSettings() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const requirePermission = allowed => {
    if (!backendReady) throw new Error(PAYROLL_BACKEND_UPDATE_REQUIRED)
    if (!allowed) throw new Error('Bạn không có quyền thực hiện thao tác này.')
  }
  const requireMonth = () => {
    if (!/^\d{4}-(0[1-9]|1[0-2])$/.test(month)) throw new Error('Vui lòng chọn tháng lương hợp lệ.')
  }
  const payload = (items = rows) => {
    requireMonth()
    if (rowsMonth !== month || !items.length) throw new Error('Hãy tính hoặc mở đúng bảng lương của tháng đã chọn trước khi tiếp tục.')
    if (draftRevision == null) throw new Error('Hãy Mở bảng nháp hoặc tính lại để lấy phiên bản bảng lương mới nhất.')
    return { month: rowsMonth, rows: items, history_id: editingHistoryId, expected_revision: draftRevision, expected_history_revision: historyRevision }
  }
  const requireEvidence = items => {
    if (hasPendingPayrollEvidence(items)) throw new Error('Còn nhân viên chờ xác nhận công hoặc cấu hình ca/đơn giá. Hãy bổ sung dữ liệu và tính lại trước khi hoàn thành, xuất hoặc gửi bảng lương.')
  }
  const calculateInto = async task => {
    requirePermission(canCalculate); requireMonth()
    const result = await task.request(`/v2/department-payroll/combined/calculate?month=${month}&source=employee`)
    if (!hasPayrollRevisions(result)) { setBackendCompatible(false); throw new Error(PAYROLL_BACKEND_UPDATE_REQUIRED) }
    if (result.month && result.month !== month) throw new Error('Máy chủ trả về sai tháng lương. Vui lòng tải lại.')
    setDraftRevision(result.draft_revision ?? null); setHistoryRevision(result.history_revision ?? null); resolveUncertain('payroll')
    setRows(result.rows || []); setRowsMonth(month); setSelected([])
    setPayrollSearch(''); setDepartmentFilter(''); setEditingHistoryId('')
    setCalculationPeriod({ start: result.start, end: result.end, source: result.source_label })
    setNotice({ type: 'success', message: `Đã tính lương nháp ${result.rows?.length || 0} nhân viên theo nguồn đã lưu của từng người, kỳ ${displayIsoDate(result.start)} – ${displayIsoDate(result.end)}.` })
  }
  const calculate = () => run('calculate-employee', calculateInto)

  const loadDraft = () => run('draft-load', async task => {
    requireMonth()
    const result = await task.request(`/v2/department-payroll/combined/draft?month=${month}`)
    if (backendReady && !hasPayrollRevisions(result)) setBackendCompatible(false)
    if (result.month && result.month !== month) throw new Error('Máy chủ trả về sai tháng lương. Vui lòng tải lại.')
    setDraftRevision(result.draft_revision ?? null); setHistoryRevision(result.history_revision ?? null); resolveUncertain('payroll')
    if (!result.rows?.length) { clearPayroll(); throw new Error('Kỳ này chưa có bảng lương nháp.') }
    setRows(result.rows); setRowsMonth(month); setSelected([])
    setPayrollSearch(''); setDepartmentFilter(''); setEditingHistoryId(result.history_id || ''); setCalculationPeriod(null)
    setNotice({ type: 'success', message: 'Đã mở bảng Lương hành chánh nháp. Nguồn lương được giữ theo bản đã lưu.' })
  })

  const editRow = (employee, key, value) => {
    if (!backendReady || !canSave || mutationRef.current?.status === 'pending') return
    invalidateSnapshot()
    setRows(items => items.map(item => item.employee_username === employee
      ? recalculate({ ...item, [key]: value }, item.calculation_config || settings[item.department]?.config || {}, key)
      : item))
  }
  const saveDraft = () => run('draft-save', async task => {
    requirePermission(canSave)
    const result = await task.request('/v2/department-payroll/combined/draft', { method: 'PUT', body: JSON.stringify(payload()) })
    setDraftRevision(result.draft_revision ?? null); setHistoryRevision(result.history_revision ?? historyRevision)
    setRows(result.rows); setNotice({ type: 'success', message: result.message })
  })
  const deleteDraft = () => run('draft-delete', async task => {
    requirePermission(canSave); requireMonth()
    if (!(await task.confirm(`Xóa bảng lương nháp tháng ${month.split('-').reverse().join('/')}? Lịch sử bảng lương đã hoàn thành được giữ nguyên.`))) return
    const expectedRevision = draftRevision ?? (await task.request(`/v2/department-payroll/combined/draft?month=${month}`)).draft_revision
    if (expectedRevision == null) throw new Error('Không lấy được phiên bản bảng lương. Vui lòng mở lại bảng nháp.')
    const result = await task.request(`/v2/department-payroll/combined/draft?month=${month}&expected_revision=${expectedRevision}`, { method: 'DELETE' })
    clearPayroll()
    setNotice({ type: 'success', message: result.message })
  })
  const recalculatePayroll = () => run('recalculate', async task => {
    requirePermission(canCalculate)
    if (!(await task.confirm('Tính lại lương theo nguồn đã lưu của từng nhân viên và dữ liệu mới nhất? Các chỉnh sửa chưa lưu trên bảng hiện tại sẽ được thay thế.'))) return
    await calculateInto(task)
  })
  const completePayroll = () => run('complete', async task => {
    requirePermission(canSave); requireEvidence(rows)
    if (historyRevision == null) throw new Error('Hãy Mở bảng nháp hoặc tính lại để lấy phiên bản lịch sử mới nhất.')
    const body = JSON.stringify(payload())
    if (!(await task.confirm(`Hoàn thành bảng Lương hành chánh tháng ${month.split('-').reverse().join('/')} và lưu vào lịch sử?`))) return
    const result = await task.request('/v2/department-payroll/combined/complete', { method: 'POST', body })
    setDraftRevision(result.draft_revision ?? null); setHistoryRevision(result.history_revision ?? null)
    setRows(result.rows); setEditingHistoryId(result.history_id || '')
    const historyResult = await task.request('/v2/department-payroll/combined/history')
    setHistory(historyResult.items || [])
    setNotice({ type: 'success', message: result.message })
  })
  const downloadFile = (file, filename) => {
    const url = URL.createObjectURL(file), anchor = document.createElement('a')
    anchor.href = url; anchor.download = filename
    document.body.appendChild(anchor); anchor.click(); anchor.remove()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  }
  const exportExcel = () => run('export', async task => {
    requirePermission(canExport); requireEvidence(visibleRows)
    const blob = await task.request('/v2/department-payroll/combined/export.xlsx', { method: 'POST', body: JSON.stringify(payload(visibleRows)), download: true })
    downloadFile(blob, `Luong_hanh_chanh_${month}.xlsx`)
  })
  const prepareShare = () => {
    setShareOpen(true)
    void run('share-prepare', async task => {
      requirePermission(canExport); requireEvidence(visibleRows)
      const body = JSON.stringify(payload(visibleRows))
      const files = await Promise.all(['png', 'pdf'].map(async type => {
        const blob = await task.request(`/v2/department-payroll/combined/export.${type}`, { method: 'POST', body, download: true })
        return new File([blob], `Luong_hanh_chanh_${month}.${type}`, { type: type === 'pdf' ? 'application/pdf' : 'image/png' })
      }))
      task.assertCurrent()
      setShareFiles({ png: files[0], pdf: files[1], isCurrent: task.isCurrent })
    })
  }
  const closeShare = () => { invalidateSnapshot() }
  const saveFile = type => {
    const file = shareFiles?.[type]
    if (!backendReady || !canExport || !file || !shareFiles.isCurrent()) return
    downloadFile(file, file.name)
  }
  const shareFile = type => {
    const file = shareFiles?.[type]
    if (!backendReady || !canExport || !file || !shareFiles.isCurrent()) return
    const isCurrent = shareFiles.isCurrent
    if (navigator.canShare?.({ files: [file] }) && navigator.share) {
      void navigator.share({ files: [file], title: 'Bảng lương hành chánh' }).catch(error => {
        if (isCurrent() && error.name !== 'AbortError') setNotice({ type: 'error', message: error.message })
      })
    } else { saveFile(type) }
    setShareOpen(false)
  }
  const sendEmail = () => run('email', async task => {
    requirePermission(canEmail)
    if (!selected.length) throw new Error('Vui lòng chọn nhân viên cần gửi email.')
    payload(); requireEvidence(rows.filter(row => selected.includes(row.employee_username)))
    if (!(await task.confirm(`Gửi ${selected.length} email bảng Lương hành chánh?`))) return
    const results = []
    for (const department of Object.keys(settings)) {
      const departmentRows = rows.filter(row => row.department === department && selected.includes(row.employee_username))
      if (departmentRows.length) results.push(await task.request('/v2/department-payroll/email', {
        method: 'POST', body: JSON.stringify({ department, month, rows: departmentRows, employees: departmentRows.map(row => row.employee_username) }),
      }))
    }
    const sent = results.reduce((sum, item) => sum + (item.sent?.length || 0), 0)
    const failed = results.reduce((sum, item) => sum + (item.failed?.length || 0), 0)
    setNotice({ type: failed ? 'error' : 'success', message: `Đã gửi ${sent} email; lỗi ${failed}.` })
  })

  const openHistory = historyId => run('history-open', async task => {
    requirePermission(canSave)
    const targetMonth = history.find(item => item.id === historyId)?.month
    if (!targetMonth) throw new Error('Hãy làm mới lịch sử trước khi mở bảng lương này.')
    const current = await task.request(`/v2/department-payroll/combined/draft?month=${targetMonth}`)
    if (current.draft_revision == null) throw new Error('Không lấy được phiên bản bảng nháp của kỳ đã chọn.')
    resolveUncertain('payroll', targetMonth)
    const result = await task.request(`/v2/department-payroll/combined/history/${encodeURIComponent(historyId)}/open?expected_revision=${current.draft_revision}`, { method: 'POST', mutationMonth: targetMonth })
    setDraftRevision(result.draft_revision ?? null); setHistoryRevision(result.history_revision ?? null)
    setMonth(result.month); setRowsMonth(result.month); setRows(result.rows || []); setSelected([]); setEditingHistoryId(result.history_id)
    setPayrollSearch(''); setDepartmentFilter(''); setCalculationPeriod(null)
    setNotice({ type: 'success', message: result.message })
  })

  const editEmployeeConfig = (group, username, key, value) => {
    if (!backendReady || !canConfig || mutationRef.current?.status === 'pending') return
    invalidateSnapshot()
    setNumericConfigDirty(true)
    setSalaryConfigTables(currentTables => ({ ...currentTables,
      [group]: (currentTables[group] || []).map(row => row.employee_username === username
        ? { ...row, [key]: Number(value), explicit_rate_fields: [...new Set([...(row.explicit_rate_fields || []), key])] } : row),
    }))
  }

  const editEmployeeSource = (username, value) => {
    if (!backendReady || !canConfig || mutationRef.current?.status === 'pending') return
    invalidateSnapshot()
    const source = salarySource(value)
    setEmployeeCatalog(items => items.map(row => row.employee_username === username ? { ...row, salary_source: source } : row))

  }

  const saveEmployeeConfigs = () => run('employee-settings-save', async task => {
    requirePermission(canConfig)
    if (employeeConfigRevision == null) throw new Error('Hãy làm mới cấu hình trước khi lưu để kiểm tra phiên bản mới nhất.')
    const result = await task.request('/v2/department-payroll/settings/employees', {
      method: 'PUT',
      body: JSON.stringify({ ...(numericConfigDirty ? { rows: [...(salaryConfigTables.operations || []), ...(salaryConfigTables.tapvu || [])] } : {}), expected_revision: employeeConfigRevision, salary_sources: employeeCatalog.map(row => ({ employee_username: row.employee_username, salary_source: salarySource(row.salary_source) })) }),
    })
    const tables = normalizeSalaryConfigTables(result.salary_config_tables || salaryConfigTables)
    const catalog = (result.salary_employee_catalog || employeeCatalog).map(row => ({ ...row, salary_source: salarySource(row.salary_source) }))
    setEmployeeCatalog(catalog)
    setSalaryConfigTables(tables); setNumericConfigDirty(false)
    setEmployeeConfigRevision(result.employee_config_revision ?? null)
    setSettingsBaseline(current => JSON.stringify([JSON.parse(current || '[{},{}]')[0], tables, catalog]))
    setNotice({ type: 'success', message: result.message })
  })

  const employeeCandidates = (group) => {
    const departments = group === 'tapvu' ? new Set(Object.keys(settings).filter(key => settings[key].config?.calculation_mode === 'monthly')) : new Set([addDepartment])
    const configured = new Set([...(salaryConfigTables.operations || []), ...(salaryConfigTables.tapvu || [])].map((row) => row.employee_username))
    const search = normalizeSearch(employeeSearch[group])
    return employeeCatalog.filter((item) => departments.has(item.department)
      && !configured.has(item.employee_username)
      && (!search || searchTextMatches([item.employee_name, item.employee_username], search)))
  }

  const addEmployeeRow = (group) => {
    if (!backendReady || !canConfig || mutationRef.current?.status === 'pending') return
    invalidateSnapshot()
    const username = pendingEmployee[group]
    const candidate = employeeCatalog.find((item) => item.employee_username === username)
    if (!candidate) {
      setNotice({ type: 'error', message: 'Vui lòng tìm và chọn một nhân viên trong đúng bộ phận.' })
      return
    }
    const config = settings[candidate.department]?.config || {}
    setNumericConfigDirty(true)
    setSalaryConfigTables((tables) => ({ ...tables, [group]: [...(tables[group] || []), { ...config, ...candidate, salary_source: salarySource(candidate.salary_source) }] }))
    setPendingEmployee((value) => ({ ...value, [group]: '' }))
    setEmployeeSearch((value) => ({ ...value, [group]: '' }))
    setNotice(null)
  }

  const removeEmployeeRow = (group, username) => {
    if (!backendReady || !canConfig || mutationRef.current?.status === 'pending') return
    invalidateSnapshot()
    setNumericConfigDirty(true)
    setSalaryConfigTables(tables => ({ ...tables, [group]: (tables[group] || []).filter(row => row.employee_username !== username) }))
  }

  const employeeConfigTable = (group, title, fields) => {
    const items = salaryConfigTables[group] || []
    const candidates = employeeCandidates(group)
    return <section ref={group === 'operations' ? hourlyRef : undefined} data-ui-key="u-38d16c658c67" className="department-config-table-section">
      <div data-ui-key="u-b189c5f017f9" className="panel-title-row"><div><h3>{title}</h3><p>Mỗi nhân viên chọn đúng một nguồn lương. Lưu cấu hình trước khi tính; nhân viên chưa có mức riêng dùng mức lương của bộ phận. Nguồn lương được chọn trong bảng đầy đủ ở trên.</p></div></div>
      <div className="department-config-add-row">
        {group === 'operations' && <label>Bộ phận<select value={addDepartment} disabled={!backendReady || !canConfig || Boolean(busy)} onChange={(event) => { setAddDepartment(event.target.value); setPendingEmployee((value) => ({ ...value, operations: '' })) }}>{Object.entries(settings).filter(([, item]) => item.config?.calculation_mode === 'hourly').map(([key, item]) => <option key={key} value={key}>{item.department_label}</option>)}</select></label>}
        <label className="department-config-search"><span>Tìm nhân viên</span><div><Search size={16} /><input value={employeeSearch[group]} disabled={!backendReady || !canConfig || Boolean(busy)} placeholder="Nhập tên hoặc tên đăng nhập…" onChange={(event) => { setEmployeeSearch((value) => ({ ...value, [group]: event.target.value })); setPendingEmployee((value) => ({ ...value, [group]: '' })) }} /></div></label>
        <label>Chọn nhân viên<select value={pendingEmployee[group]} disabled={!backendReady || !canConfig || Boolean(busy)} onChange={(event) => setPendingEmployee((value) => ({ ...value, [group]: event.target.value }))}><option value="">-- Chọn nhân viên --</option>{candidates.map((item) => <option key={item.employee_username} value={item.employee_username}>{item.employee_name} · {item.employee_username}</option>)}</select></label>
        <button data-ui-key="u-42941a1c0373" data-ui-label-default="Thêm dòng" className="secondary-button" type="button" disabled={!backendReady || !canConfig || Boolean(busy) || !pendingEmployee[group]} onClick={() => addEmployeeRow(group)}><Plus size={16} /><UiCustomText uiKey="u-42941a1c0373"> Thêm dòng</UiCustomText></button>
      </div>
      <div className="responsive-data-table department-config-table" tabIndex={0} role="region" aria-label={`${title} · cấu hình lương`}><table data-ui-key="u-ee5aa400105c">
        <thead><tr><th className="department-config-index-column" data-ui-key="u-014a14092a84" data-ui-label-default="TT"><UiCustomText uiKey="u-014a14092a84">TT</UiCustomText></th><th className="department-config-name-column" data-ui-key="u-11eb1864484f" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-11eb1864484f">Nhân viên</UiCustomText></th><th data-ui-key="u-fe55a3a13f53" data-ui-label-default="Bộ phận"><UiCustomText uiKey="u-fe55a3a13f53">Bộ phận</UiCustomText></th>{fields.map(([, label]) => <th data-ui-key="u-c406e1406f17" key={label}>{label}</th>)}<th>Nguồn tính lương</th><th data-ui-key="u-2e364e25a4c3" /></tr></thead>
        <tbody>{items.map((row, index) => <tr key={row.employee_username}>
          <td className="department-config-index-column">{index + 1}</td>
          <td className="department-config-name-column"><div className="department-config-identity"><strong>{row.employee_name}</strong><small>{row.employee_username}</small></div></td>
          <td><strong>{row.department_label}</strong></td>
          {fields.map(([key]) => <td key={key}><VeraMoneyInput className="payroll-money-input" disabled={!backendReady || !canConfig || Boolean(busy)} value={row[key]} onChange={(event) => editEmployeeConfig(group, row.employee_username, key, event.target.value)} /></td>)}
          <td>{salarySourceLabel(employeeCatalog.find(item => item.employee_username === row.employee_username)?.salary_source ?? row.salary_source)}</td>
          <td><button data-ui-key="u-e63c7076f12d" className="icon-button danger" type="button" title="Xóa mức lương riêng; dùng lại mức bộ phận và giữ nguồn lương đã chọn" disabled={!backendReady || !canConfig || Boolean(busy)} onClick={() => removeEmployeeRow(group, row.employee_username)}><Trash2 size={15} /></button></td>
        </tr>)}</tbody>
      </table></div>
      {!items.length && <div className="setup-note">Chưa có nhân viên đang làm việc trong nhóm này.</div>}
    </section>
  }

  const sourceRows = employeeCatalog.filter(row => searchTextMatches([row.employee_name, row.employee_username, row.department_label], sourceSearch))
  const sourceConfigTable = <section className="department-payroll-source-section">
    <div className="panel-title-row"><div><h3>NGUỒN TÍNH LƯƠNG THEO NHÂN VIÊN</h3><p>Toàn bộ nhân viên hành chánh, kể cả người đang dùng mức lương chung của bộ phận. Chọn đúng một nguồn rồi Lưu cấu hình. Chưa chọn riêng sẽ dùng Thống kê; đổi nguồn không thay đổi mức lương.</p></div></div>
    <label>Tìm nhân viên theo nguồn lương<input aria-label="Tìm cấu hình nguồn lương" value={sourceSearch} disabled={mutationPending} onChange={event => setSourceSearch(event.target.value)} placeholder="Tên, tên đăng nhập hoặc bộ phận…" /></label>
    <div className="responsive-data-table department-payroll-source-table" role="region" aria-label="Nguồn lương toàn bộ nhân viên hành chánh" tabIndex={0}><table>
      <colgroup><col className="department-source-name-column" /><col className="department-source-department-column" /><col className="department-source-choice-column" /></colgroup>
      <thead><tr><th scope="col">Nhân viên</th><th scope="col">Bộ phận</th><th scope="col">Nguồn tính lương</th></tr></thead>
      <tbody>{sourceRows.map(row => <tr key={row.employee_username}>
        <td><div className="department-payroll-source-identity"><strong>{row.employee_username}</strong><small>{row.employee_name}</small></div></td><td>{row.department_label}</td>
        <td><div className="department-payroll-source-options" role="radiogroup" aria-label={`Nguồn lương ${row.employee_name}`}>
          {['schedule', 'attendance'].map(source => <label key={source}><input type="radio" name={`salary-source-${row.employee_username}`} value={source} checked={salarySource(row.salary_source) === source} disabled={!backendReady || !canConfig || Boolean(busy)} onChange={() => editEmployeeSource(row.employee_username, source)} /><span>{source === 'schedule' ? 'Tính lương từ Thống kê' : 'Tính từ Chấm công'}</span></label>)}
        </div></td>
      </tr>)}</tbody>
    </table></div>
    {!sourceRows.length && <p role="status">Không có nhân viên phù hợp.</p>}
  </section>

  if (settingsOnly) return <div ref={pageRef} className="feature-page department-payroll-page department-payroll-config-page">
    <section data-ui-key="u-0a9ecdd6d190" className="panel department-payroll-panel">
      <div data-ui-key="u-367c7a50f712" className="panel-title-row"><div><h2><Settings2 size={18} /> CẤU HÌNH LƯƠNG THEO NHÂN VIÊN</h2><p>Bảng 1 gồm các bộ phận Lương giờ. Bảng 2 gồm các bộ phận Lương tháng. Chọn hình thức lương trong menu Nhân sự.</p></div><div className="list-actions">{canConfig && <button className="primary-button" type="button" disabled={Boolean(busy) || writeBlocked} onClick={saveEmployeeConfigs}><Save size={16} />Lưu cấu hình</button>}<button className="secondary-button" type="button" onClick={() => hourlyRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })}>BẢNG 1 · LƯƠNG GIỜ</button><button data-ui-key="u-d2f1dad4aa43" data-ui-label-default="Làm mới" className="secondary-button" type="button" onClick={loadSettings} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'settings-load' ? 'spin' : ''} /><UiCustomText uiKey="u-d2f1dad4aa43"> Làm mới</UiCustomText></button></div></div>
      <StableFeedback>{notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}</StableFeedback>
      {backendCompatible === false && <div className="error-box department-payroll-backend-required" role="status">{PAYROLL_BACKEND_UPDATE_REQUIRED}</div>}
      {mutationPending && <p role="status">Đang chờ máy chủ xác nhận thao tác {mutation.resource === 'settings' ? 'cấu hình' : `bảng lương tháng ${mutation.month.split('-').reverse().join('/')}`}. Chưa thể lưu tiếp.</p>}
      {mutationUncertain && <div className="error-box" role="status">{mutation.conflict ? 'Bảng lương hoặc cấu hình đã được cập nhật ở nơi khác.' : 'Chưa xác nhận được kết quả thao tác trước.'} Hãy {settingsOnly ? 'Làm mới cấu hình' : 'Mở bảng nháp hoặc tính lại'} để kiểm tra phiên bản hiện tại trước khi lưu tiếp.</div>}
      {sourceConfigTable}
      {employeeConfigTable('operations', 'BẢNG 1 · LƯƠNG GIỜ', operationsEmployeeFields)}
      {employeeConfigTable('tapvu', 'BẢNG 2 · LƯƠNG THÁNG', tapvuEmployeeFields)}
      <div className="setup-note">Email bảng lương các bộ phận dùng cùng mẫu chuẩn đang áp dụng cho Leader/Nhân viên.</div>
      {canConfig ? <UiToolbar data-ui-key="u-20f37bcbdc7b" className="list-actions department-payroll-actions"><button data-ui-key="u-76a59707a7cb" className="primary-button" type="button" disabled={Boolean(busy) || writeBlocked} onClick={saveEmployeeConfigs}><Save size={16} /> {busy === 'employee-settings-save' ? 'Đang lưu…' : 'Lưu toàn bộ cấu hình'}</button></UiToolbar> : <div className="error-box">Chỉ Admin được thay đổi cấu hình lương và phụ cấp.</div>}
    </section>
  </div>

  return <div ref={pageRef} className="feature-page department-payroll-page">
    <PayrollHistorySearch items={history.map(item => ({ id: item.id, label: `Tháng ${item.month_label}`, searchText: `${item.month || ''} ${item.saved_by || ''} ${item.saved_at ? formatVeraDateTime(item.saved_at) : ''}`, description: `${item.employee_count} nhân viên · Thực nhận ${money(item.total_net)}` }))} onEdit={backendReady && canSave ? openHistory : undefined} disabled={Boolean(busy)} />
    <section data-ui-key="u-fe386b14128e" className="panel department-payroll-panel">
      <div data-ui-key="u-0d51bd20233a" className="panel-title-row"><div><h2>LƯƠNG HÀNH CHÁNH</h2></div></div>
      <StableFeedback>{notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}</StableFeedback>
      {backendCompatible === false && <div className="error-box department-payroll-backend-required" role="status">{PAYROLL_BACKEND_UPDATE_REQUIRED}</div>}
      {mutationPending && <p role="status">Đang chờ máy chủ xác nhận thao tác {mutation.resource === 'settings' ? 'cấu hình' : `bảng lương tháng ${mutation.month.split('-').reverse().join('/')}`}. Chưa thể lưu tiếp.</p>}
      {mutationUncertain && <div className="error-box" role="status">{mutation.conflict ? 'Bảng lương hoặc cấu hình đã được cập nhật ở nơi khác.' : 'Chưa xác nhận được kết quả thao tác trước.'} Hãy {settingsOnly ? 'Làm mới cấu hình' : 'Mở bảng nháp hoặc tính lại'} để kiểm tra phiên bản hiện tại trước khi lưu tiếp.</div>}
      <UiToolbar data-ui-key="u-f89a73ac8e61" className="department-payroll-toolbar">
        <label>Tháng lương<input type="month" value={month} disabled={busy === 'settings-load' || mutationPending} onChange={event => changeMonth(event.target.value)} /></label>
        <button className="primary-button department-payroll-calculate" disabled={!backendReady || Boolean(busy) || !canCalculate} onClick={calculate}><CalendarDays size={16} /><span>Tính lương theo cấu hình</span></button>
        <button data-ui-key="u-00757540fcc5" data-ui-label-default="Mở bảng nháp" className="secondary-button" disabled={Boolean(busy)} onClick={loadDraft}>{busy === 'draft-load' ? 'Đang mở…' : <UiCustomText uiKey="u-00757540fcc5">Mở bảng nháp</UiCustomText>}</button>
        <button type="button" className="secondary-button" disabled={!backendReady || Boolean(busy) || !rows.length || !canCalculate} onClick={recalculatePayroll}><RefreshCw size={16} />Tính lại lương</button>
        {canSave && <button type="button" className="danger-button department-payroll-delete-draft" disabled={Boolean(busy) || writeBlocked} onClick={deleteDraft}><Trash2 size={16} />{busy === 'draft-delete' ? 'Đang xóa…' : 'Xóa bảng lương nháp'}</button>}
      </UiToolbar>

      <p className="department-payroll-filter-note">Tính toàn bộ nhân viên theo nguồn Thống kê hoặc Chấm công đã lưu riêng trong Cấu hình lương. Tính lại sẽ dùng cấu hình mới nhất.</p>
      {!!rows.length && <>
        {calculationPeriod && <div className="setup-note"><CalendarDays size={16} /> Lương nháp từ {calculationPeriod.source}: {displayIsoDate(calculationPeriod.start)} – {displayIsoDate(calculationPeriod.end)}. Tháng hiện tại chỉ tính đến hôm nay.</div>}
        {editingHistoryId && <div className="setup-note"><History size={16} /> Đang sửa bảng lương đã lưu. Khi bấm Hoàn thành bảng lương, bản lịch sử này sẽ được cập nhật và giữ nguyên mã.</div>}

        <div className="department-payroll-summary"><span>Nhân viên theo bộ lọc<strong>{visibleRows.length}</strong></span><span>Tổng ứng lương theo bộ lọc<strong>{money(totalAdvance)}</strong></span><span>Tổng thực nhận theo bộ lọc<strong>{visiblePendingEvidence ? 'Chờ đủ dữ liệu' : money(totalNet)}</strong></span></div>
        {pendingEvidence && <div className="error-box" role="status">Còn nhân viên chờ xác nhận công hoặc cấu hình ca/đơn giá. Có thể lưu nháp; chưa thể hoàn thành toàn bộ bảng hoặc xuất/gửi những dòng đang chờ.</div>}
        <p className="department-payroll-filter-note">Bộ lọc áp dụng cho bảng, tổng tiền và Excel. Lưu nháp và Hoàn thành vẫn lưu toàn bộ bảng lương.</p>
        <section data-ui-key="u-64dcbeb00036" className="salary-advance-panel">
          <div data-ui-key="u-8f74b397bc4e" className="panel-title-row"><div><h3><Banknote size={17} /> NHÂN VIÊN ỨNG LƯƠNG</h3><p>Nhập số tiền đã ứng; hệ thống tự trừ ngay vào Thực nhận của bảng lương hiện tại.</p></div></div>
          <div className="salary-advance-grid">{rows.map((row) => <label key={`advance-${row.employee_username}`}><span>{row.employee_name}<small>{row.department_label}</small></span><VeraMoneyInput className="payroll-money-input" disabled={!backendReady || !canSave || Boolean(busy)} value={row.advance} onChange={(event) => editRow(row.employee_username, 'advance', event.target.value)} /></label>)}</div>
        </section>
        <UiToolbar data-ui-key="u-9f377bd94706" className="list-actions department-payroll-actions department-payroll-top-actions"><div className="department-payroll-filter-fields"><label className="department-payroll-table-search">Tìm nhân viên<LiveTourSearchSelect hideLabel label="Tìm nhân viên" disabled={mutationPending} value={payrollSearch} searchValue={payrollSearch} options={rows.filter(row => !departmentFilter || row.department === departmentFilter).map(row => ({ value: row.employee_username, label: row.employee_name || row.employee_username, detail: row.employee_username, displayLabel: `${row.employee_name || row.employee_username} · ${row.employee_username}` }))} onSearch={changeSearch} onChange={changeSearch} placeholder="Nhập tên hoặc tên đăng nhập…" emptyLabel="Tất cả nhân viên" /></label><label className="department-payroll-department-filter">Bộ phận<select aria-label="Lọc bộ phận bảng lương" disabled={mutationPending} value={departmentFilter} onChange={event => changeDepartment(event.target.value)}><option value="">Tất cả bộ phận</option>{rowDepartments.map(([code, label]) => <option key={code} value={code}>{label}</option>)}</select></label></div>{canSave && <button data-ui-key="u-d8d128bf8ea0" data-ui-label-default="Lưu bảng nháp" className="secondary-button" disabled={Boolean(busy) || writeBlocked} onClick={saveDraft}><Save size={16} />{busy === 'draft-save' ? 'Đang lưu…' : <UiCustomText uiKey="u-d8d128bf8ea0"> Lưu bảng nháp</UiCustomText>}</button>}{canSave && <button data-ui-key="u-da44815b5034" data-ui-label-default="Hoàn thành bảng lương" className="primary-button" disabled={Boolean(busy) || pendingEvidence || writeBlocked} onClick={completePayroll}><CheckCircle2 size={16} /><UiCustomText uiKey="u-da44815b5034"> Hoàn thành bảng lương</UiCustomText></button>}{canEmail && <><button data-ui-key="u-d49687da041e" data-ui-label-default="Chọn tất cả có email" className="secondary-button" type="button" disabled={!backendReady || Boolean(busy)} onClick={() => { invalidateSnapshot(); setSelected(visibleRows.filter(row => !hasPendingPayrollEvidence([row]) && String(row.email || '').includes('@')).map(row => row.employee_username)) }}><Mail size={15} /><UiCustomText uiKey="u-d49687da041e"> Chọn tất cả có email</UiCustomText></button><button data-ui-key="u-af8e39d106bb" data-ui-label-default="Bỏ chọn" className="secondary-button" type="button" disabled={!backendReady || Boolean(busy)} onClick={() => { invalidateSnapshot(); setSelected([]) }}><UiCustomText uiKey="u-af8e39d106bb">Bỏ chọn</UiCustomText></button></>}{canEmail && <button data-ui-key="u-08d9057d122b" className="secondary-button" disabled={!backendReady || Boolean(busy) || !selected.length || selectedPendingEvidence} onClick={sendEmail}><Send size={16} /> <Mail size={14} /> Gửi email ({selected.length})</button>}{canExport && <button data-ui-key="u-ad79c9ff49c8" data-ui-label-default="Xuất excel" className="secondary-button" disabled={!backendReady || Boolean(busy) || !visibleRows.length || visiblePendingEvidence} onClick={exportExcel}><Download size={16} /><UiCustomText uiKey="u-ad79c9ff49c8"> Xuất excel</UiCustomText></button>}{canExport && <button type="button" className="secondary-button" disabled={!backendReady || Boolean(busy) || !visibleRows.length || visiblePendingEvidence} onClick={prepareShare}><Share2 size={16} />Chia sẻ</button>}</UiToolbar>
        <dialog ref={shareDialog} className="department-payroll-share-dialog" aria-label="Chia sẻ bảng lương" onCancel={closeShare}>
          <h3>Chia sẻ bảng lương</h3>
          <div className="department-payroll-share-options">
            <div className="department-payroll-share-format">
              <button type="button" className="secondary-button" disabled={!backendReady || !shareFiles} onClick={() => shareFile('png')}>Ảnh PNG</button>
              <button type="button" className="secondary-button" disabled={!backendReady || !shareFiles} onClick={() => saveFile('png')}><Download size={16} />Lưu ảnh</button>
            </div>
            <div className="department-payroll-share-format">
              <button type="button" className="secondary-button" disabled={!backendReady || !shareFiles} onClick={() => shareFile('pdf')}>PDF</button>
              <button type="button" className="secondary-button" disabled={!backendReady || !shareFiles} onClick={() => saveFile('pdf')}><Download size={16} />Lưu PDF</button>
            </div>
            <button type="button" className="secondary-button" onClick={closeShare}>Đóng</button>
            {busy === 'share-prepare' && <span role="status">Đang tạo file…</span>}
          </div>
        </dialog>
        <div className="responsive-data-table department-payroll-table"><table data-ui-key="u-5b7cb5285f2e"><thead><tr><th data-ui-key="u-7686681f16f7" data-ui-label-default="Gửi"><UiCustomText uiKey="u-7686681f16f7">Gửi</UiCustomText></th><th data-ui-key="u-66c870616026" data-ui-label-default="TT"><UiCustomText uiKey="u-66c870616026">TT</UiCustomText></th><th data-ui-key="u-4f0fce3caf56" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-4f0fce3caf56">Nhân viên</UiCustomText></th><th data-ui-key="u-d4304a915425" data-ui-label-default="Bộ phận"><UiCustomText uiKey="u-d4304a915425">Bộ phận</UiCustomText></th><th className="payroll-hours-column" data-ui-key="u-bcd797055bad" data-ui-label-default="Ngày công"><UiCustomText uiKey="u-bcd797055bad">Ngày công</UiCustomText></th><th className="payroll-hours-column" data-ui-key="u-b67ed3d40c39" data-ui-label-default="Giờ Ca 1"><UiCustomText uiKey="u-b67ed3d40c39">Giờ Ca 1</UiCustomText></th><th className="payroll-hours-column" data-ui-key="u-e9f4fe60b599" data-ui-label-default="Ca 2 trước 22h"><UiCustomText uiKey="u-e9f4fe60b599">Ca 2 trước 22h</UiCustomText></th><th className="payroll-hours-column" data-ui-key="u-d6b67e042cda" data-ui-label-default="Ca 2 sau 22h"><UiCustomText uiKey="u-d6b67e042cda">Ca 2 sau 22h</UiCustomText></th><th data-ui-key="u-a16a026c7a8b" data-ui-label-default="Tiền lương"><UiCustomText uiKey="u-a16a026c7a8b">Tiền lương</UiCustomText></th>{editableFields.map(([, label]) => <th data-ui-key="u-ece4a4df8e43" key={label}>{label}</th>)}<th data-ui-key="u-4adc40dcdb1a" data-ui-label-default="Tổng lương"><UiCustomText uiKey="u-4adc40dcdb1a">Tổng lương</UiCustomText></th><th className="department-payroll-net-column" data-ui-key="u-c286089dd0b6" data-ui-label-default="Thực nhận"><UiCustomText uiKey="u-c286089dd0b6">Thực nhận</UiCustomText></th></tr></thead><tbody>{visibleRows.map((row) => <tr key={row.employee_username}><td data-label="Gửi email"><input type="checkbox" aria-label={`Chọn gửi email ${row.employee_name}`} checked={selected.includes(row.employee_username)} disabled={!backendReady || !canEmail || Boolean(busy) || hasPendingPayrollEvidence([row])} onChange={() => { invalidateSnapshot(); setSelected(items => items.includes(row.employee_username) ? items.filter(item => item !== row.employee_username) : [...items, row.employee_username]) }} /></td><td data-label="TT">{row.tt}</td><td data-label="Nhân viên"><div className="department-payroll-identity"><strong>{row.employee_username}</strong><span>{row.employee_name}</span><span>{row.email || 'Chưa có email'}</span><small>Nguồn lương: {salarySourceLabel(row.calculation_source)}</small></div>{row.incomplete_days > 0 && <small className="attendance-warning">{row.incomplete_days} ngày thiếu đủ FaceID</small>}</td><td data-label="Bộ phận"><strong>{row.department_label}</strong></td><td className="payroll-hours-column" data-label="Ngày công">{row.work_days}</td><td className="payroll-hours-column" data-label="Giờ Ca 1">{['tapvu', 'support'].includes(row.department) ? '' : row.hours_ca1}</td><td className="payroll-hours-column" data-label="Ca 2 trước 22h">{['tapvu', 'support'].includes(row.department) ? '' : row.hours_ca2_before_22}</td><td className="payroll-hours-column" data-label="Ca 2 sau 22h">{['tapvu', 'support'].includes(row.department) ? '' : row.hours_ca2_after_22}</td><td data-label="Tiền lương" className="money-cell">{hasPendingPayrollEvidence([row]) ? payrollPendingLabel(row) : money(row.salary)}</td>{editableFields.map(([key, label]) => <td key={key} data-label={label} className={['violation_penalty', 'late_penalty'].includes(key) && Number(row[key]) > 0 ? 'payroll-penalty-positive' : undefined}><VeraMoneyInput className="payroll-money-input" aria-label={`${label} ${row.employee_name}`} disabled={!backendReady || !canSave || Boolean(busy)} style={{ width: `${Math.max(6, String(row[key] ?? '').replace(/\D/g, '').replace(/\B(?=(\d{3})+(?!\d))/g, '.').length + 1)}ch` }} value={row[key]} onChange={(event) => editRow(row.employee_username, key, event.target.value)} />{key === 'late_penalty' && Number(row.unpaid_late_wage || row.late_penalty_credit) > 0 && <small className="department-payroll-late-credit">Lương thời gian trễ không được tính: {money(row.unpaid_late_wage ?? row.late_penalty_credit)} · Phạt trễ trừ thêm: {money(row.effective_late_penalty ?? Math.max(0, Number(row.late_penalty || 0) - Number(row.late_penalty_credit || 0)))}.</small>}</td>)}<td data-label="Tổng lương" className="money-cell"><strong>{hasPendingPayrollEvidence([row]) ? payrollPendingLabel(row) : money(row.total_salary)}</strong></td><td data-label="Thực nhận" className="money-cell department-payroll-net-column"><strong>{hasPendingPayrollEvidence([row]) ? payrollPendingLabel(row) : money(row.net_salary)}</strong></td></tr>)}</tbody></table></div>
        {!visibleRows.length && <p role="status">Không có nhân viên phù hợp bộ lọc.</p>}

        <StableFeedback>{busy === 'draft-save' || busy === 'draft-load'
          ? <div role="status">{busy === 'draft-save' ? 'Đang lưu bảng lương nháp…' : 'Đang mở bảng lương nháp…'}</div>
          : notice && <div role="status" className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}</StableFeedback>
      </>}
    </section>
    <section data-ui-key="u-aacee11d5e23" className="panel department-payroll-history">
      <div data-ui-key="u-af5bcde4d1db" className="panel-title-row"><div><h2><History size={18} /> LỊCH SỬ BẢNG LƯƠNG</h2></div><button data-ui-key="u-36ab47558e09" data-ui-label-default="Làm mới" className="secondary-button" type="button" onClick={loadSettings} disabled={Boolean(busy)}><RefreshCw size={16} /><UiCustomText uiKey="u-36ab47558e09"> Làm mới</UiCustomText></button></div>
      <button type="button" className="secondary-button" aria-expanded={historyOpen} aria-controls="hc-payroll-history-content" onClick={() => setHistoryOpen(value => !value)}>{historyOpen ? 'Ẩn lịch sử' : 'Hiện lịch sử'}</button>
      <div id="hc-payroll-history-content" hidden={!historyOpen}>
      <div className="department-history-list">{history.map((item) => <article key={item.id}><div><strong>Tháng {item.month_label}</strong><span>{item.employee_count} nhân viên · {item.source_label || 'Chấm công'} · Thực nhận {money(item.total_net)}</span><small>Lưu bởi {item.saved_by || '—'} · {item.saved_at ? formatVeraDateTime(item.saved_at) : '—'}</small></div>{canSave && <button data-ui-key="u-446648a6be25" data-ui-label-default="Mở để sửa" className="secondary-button" type="button" disabled={!backendReady || Boolean(busy)} onClick={() => openHistory(item.id)}><History size={15} /><UiCustomText uiKey="u-446648a6be25"> Mở để sửa</UiCustomText></button>}</article>)}</div>
      {!history.length && <div className="setup-note">Chưa có lịch sử bảng Lương hành chánh.</div>}
      </div>
    </section>
  </div>
}
