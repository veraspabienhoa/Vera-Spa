import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import ClearableSearchInput from '../components/ClearableSearchInput'
import { searchTextMatches } from '../lib/searchText'
import { ArrowRightCircle, CheckCircle2, Download, Edit3, Mail, Plus, RefreshCw, Save, Search, Settings2, Trash2, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { getCurrentSession } from '../lib/supabase'
import VeraDateInput from '../components/VeraDateInput'
import VeraMoneyInput from '../components/VeraMoneyInput'
import './PayrollPageEnhanced.css'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const currentMonth = () => {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}
const currentPeriodNo = () => new Date().getDate() <= 15 ? 1 : 2
const periodDates = (month, periodNo) => {
  const [year, monthNumber] = month.split('-').map(Number)
  const startDay = periodNo === 1 ? 1 : 16
  const endDay = periodNo === 1 ? 15 : new Date(year, monthNumber, 0).getDate()
  const iso = (day) => `${year}-${String(monthNumber).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  return { start: iso(startDay), end: iso(endDay) }
}
const CONFIG_DEFAULT = { default_living_expense: 150000, default_locker_support: 80000, leader_responsibility_allowance: 0 }
const EDIT_LABELS = {
  'Tiền Hỗ Trợ Hoàn Lại': 'Trách nhiệm / hỗ trợ',
  'Hoàn trả tiền tích lũy': 'Hoàn trả tích lũy',
  'Tích lũy': 'Tích lũy',
  'Chi Phí Sinh Hoạt': 'Phí sinh hoạt',
  'Tiền phạt trong tháng': 'Vi phạm kỳ này',
  'Vi phạm kỳ trước': 'Nợ vi phạm kỳ trước',
  'Tiền ứng lương': 'Tiền ứng',
  'Tiền hỗ trợ Locker': 'Hỗ trợ Locker',
}

async function enhancementRequest(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

function normalizeSearch(value) {
  return String(value || '')
    .normalize('NFD')
    .replace(/[\u0300-\u036f]/g, '')
    .replace(/đ/g, 'd')
    .replace(/Đ/g, 'D')
    .toLowerCase()
    .trim()
}

function recalculate(row) {
  const value = (field) => Number(row[field] || 0)
  const next = { ...row }
  if (value('Tiền Lương') === 0) {
    next['Chi Phí Sinh Hoạt'] = 0
    next['Tiền hỗ trợ Locker'] = 0
  }
  next['Số tiền thực nhận'] = value('Tiền Lương') + value('Tiền Hỗ Trợ Hoàn Lại')
    + value('Hoàn trả tiền tích lũy') - value('Tích lũy') - value('Chi Phí Sinh Hoạt')
    - value('Tiền phạt trong tháng') - value('Vi phạm kỳ trước')
    - value('Tiền ứng lương') - value('Tiền hỗ trợ Locker')
  return next
}

function isNonPositive(row) {
  return Number(row?.['Số tiền thực nhận'] || 0) <= 0
}

function ObligationGroup({ group }) {
  const isNegative = group.type === 'Âm thực nhận'
  const summary = group.summary || []
  const details = group.details || []
  return <div className="payroll-obligation-group">
    <h3>{isNegative ? '🔴 Nợ do Thực nhận âm' : '⏭️ Nghĩa vụ Vi phạm Admin chủ động tạm hoãn'}</h3>
    <div className="responsive-data-table"><table data-ui-key="u-0ce98523f8d6"><thead><tr><th data-ui-key="u-9243e5d76744" data-ui-label-default="Tên nhân viên"><UiCustomText uiKey="u-9243e5d76744">Tên nhân viên</UiCustomText></th><th data-ui-key="u-cfc4df9087f5">{isNegative ? 'Tổng còn nợ' : 'Tổng tạm hoãn'}</th><th data-ui-key="u-f1945ce7cce5">{isNegative ? 'Số kỳ còn nợ' : 'Số kỳ tạm hoãn'}</th><th data-ui-key="u-db415a7bca0a">{isNegative ? 'Kỳ nợ gần nhất' : 'Kỳ tạm hoãn gần nhất'}</th><th data-ui-key="u-2ec24143de2a" data-ui-label-default="Bắt đầu trừ từ"><UiCustomText uiKey="u-2ec24143de2a">Bắt đầu trừ từ</UiCustomText></th></tr></thead><tbody>{summary.map((item) => <tr key={`${group.type}-${item.employee_name}`}><td>{item.employee_name}</td><td>{money(item.total)}</td><td className="center">{item.period_count}</td><td>{item.latest_period}</td><td>{item.due_from}</td></tr>)}</tbody></table></div>
    {!summary.length && <div className="setup-note">Không có khoản đang mở.</div>}
    {details.length > 0 && <details className="payroll-obligation-details"><summary>🔎 Xem chi tiết từng kỳ ({details.length})</summary><div className="responsive-data-table"><table data-ui-key="u-c38e433e7cf0"><thead><tr><th data-ui-key="u-e49b6cd26844" data-ui-label-default="Tên nhân viên"><UiCustomText uiKey="u-e49b6cd26844">Tên nhân viên</UiCustomText></th><th data-ui-key="u-820c941c1de2" data-ui-label-default="Số tiền"><UiCustomText uiKey="u-820c941c1de2">Số tiền</UiCustomText></th><th data-ui-key="u-258f689339cf" data-ui-label-default="Kỳ phát sinh từ"><UiCustomText uiKey="u-258f689339cf">Kỳ phát sinh từ</UiCustomText></th><th data-ui-key="u-00b2bf07008a" data-ui-label-default="Kỳ phát sinh đến"><UiCustomText uiKey="u-00b2bf07008a">Kỳ phát sinh đến</UiCustomText></th><th data-ui-key="u-cfd8bd47bbae" data-ui-label-default="Bắt đầu trừ từ"><UiCustomText uiKey="u-cfd8bd47bbae">Bắt đầu trừ từ</UiCustomText></th><th data-ui-key="u-3504ca240e92" data-ui-label-default="Nội dung"><UiCustomText uiKey="u-3504ca240e92">Nội dung</UiCustomText></th><th data-ui-key="u-333847b835fe" data-ui-label-default="Trạng thái"><UiCustomText uiKey="u-333847b835fe">Trạng thái</UiCustomText></th></tr></thead><tbody>{details.map((item, index) => <tr key={`${group.type}-${item.employee_name}-${item.period_start}-${index}`}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.period_start}</td><td>{item.period_end}</td><td>{item.due_from}</td><td>{item.content}</td><td>{item.status}</td></tr>)}</tbody></table></div></details>}
  </div>
}

export default function PayrollPageEnhanced({ user, activeTab = 'calculate', onTabChange }) {
  usePageRefresh(() => reload(), () => Boolean(busy || JSON.stringify(config) !== configBaseline))
  const permissions = user?.permissions || {}
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const canCalculate = isAdmin || permissions.payroll_calculate
  const canEditConfig = isAdmin || permissions.payroll_config_edit
  const canManageObligations = isAdmin || permissions.payroll_penalty_obligation
  const canSyncLegacy = isAdmin || permissions.payroll_history_edit
  const canDeleteHistory = isAdmin || permissions.payroll_history_edit
  const canSave = isAdmin || permissions.payroll_save
  const canEmail = isAdmin || permissions.payroll_email
  const canExport = isAdmin || permissions.payroll_export

  const [batch, setBatch] = useState('')
  const [employee, setEmployee] = useState('')
  const [history, setHistory] = useState({ records: [], batches: [], employees: [] })
  const [savedBatches, setSavedBatches] = useState([])
  const [month, setMonth] = useState(currentMonth())
  const [periodNo, setPeriodNo] = useState(currentPeriodNo())
  const [draft, setDraft] = useState(null)
  const [draftSearch, setDraftSearch] = useState('')
  const [draftNonPositiveOnly, setDraftNonPositiveOnly] = useState(false)
  const [draftFormerOnly, setDraftFormerOnly] = useState(false)
  const [selected, setSelected] = useState([])
  const [historySelected, setHistorySelected] = useState([])
  const [searchSelectionMode, setSearchSelectionMode] = useState(false)
  const [config, setConfig] = useState(CONFIG_DEFAULT)
  const [configBaseline, setConfigBaseline] = useState(() => JSON.stringify(CONFIG_DEFAULT))
  const [accumulationRefunds, setAccumulationRefunds] = useState([])
  const [formerEmployees, setFormerEmployees] = useState([])
  const [refundForm, setRefundForm] = useState({ employee_name: '', amount: '', note: 'Hoàn trả tiền tích lũy khi nghỉ việc' })
  const [obligations, setObligations] = useState([])
  const [obligationGroups, setObligationGroups] = useState([])
  const [obligationForm, setObligationForm] = useState({ employee_name: '', amount: '', content: 'Chưa hoàn thành nghĩa vụ Vi phạm', due_from: '' })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [emailProgress, setEmailProgress] = useState(null)
  const historyRequest = useRef(0)
  const [autoOpenLatestDraft, setAutoOpenLatestDraft] = useState(true)

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { await callback() } catch (error) { setNotice({ type: 'error', message: error.message }) } finally { setBusy('') }
  }

  const loadHistory = async (batchOverride = batch, employeeOverride = employee) => {
    const requestId = ++historyRequest.current
    const result = await veraApi.payrollHistory(batchOverride, employeeOverride)
    if (requestId === historyRequest.current) {
      setHistory(result)
      setHistorySelected([])
    }
    return result
  }

  const loadSavedBatches = async () => {
    const result = await enhancementRequest('/v2/payroll/saved-batches')
    setSavedBatches(result.saved_batches || [])
    return result
  }

  const loadSupporting = async () => {
    if (canCalculate || canEditConfig) {
      const result = await veraApi.payrollConfig()
      setConfig(result.config || CONFIG_DEFAULT); setConfigBaseline(JSON.stringify(result.config || CONFIG_DEFAULT))
    }
    if (isAdmin && canEditConfig) {
      const result = await veraApi.payrollAccumulationRefunds()
      setAccumulationRefunds(result.refunds || [])
      setFormerEmployees(result.employees || [])
    }
    if (canManageObligations) {
      const result = await veraApi.payrollObligations()
      setObligations(result.obligations || [])
      setObligationGroups(result.groups || [])
    }
  }

  const reload = () => run('load', async () => {
    await Promise.all([loadHistory(), loadSavedBatches(), loadSupporting()])
  })

  useEffect(() => { void reload() }, [batch, employee]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const reopen = (event) => {
      const result = event.detail || {}
      if (!result.draft || !result.month || !result.period_no) return
      setAutoOpenLatestDraft(false)
      setMonth(String(result.month))
      setPeriodNo(Number(result.period_no))
      setDraft(result.draft)
      setDraftSearch('')
      setSelected((result.draft.rows || []).map((row) => row['Tên Hệ thống']))
      setNotice({ type: 'success', message: result.message })
      window.setTimeout(() => document.querySelector('.payroll-page-enhanced .payroll-draft-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
    }
    window.addEventListener('vera:payroll-reopen', reopen)
    return () => window.removeEventListener('vera:payroll-reopen', reopen)
  }, [])

  useEffect(() => {
    let active = true
    if (!canCalculate || !month) return () => { active = false }
    setDraft(null)
    setDraftSearch('')
    setSelected([])
    veraApi.payrollDraft(month, periodNo, autoOpenLatestDraft)
      .then((result) => {
        if (!active) return
        const saved = result.draft || null
        if (result.fallback_used && saved) {
          setMonth(result.selected_month)
          setPeriodNo(Number(result.selected_period_no))
          setNotice({
            type: 'success',
            message: `Kỳ hiện tại chưa có dữ liệu. Đã tự mở bản nháp gần nhất: ${saved.period_label}.`,
          })
        }
        setAutoOpenLatestDraft(false)
        setDraft(saved)
        setSelected((saved?.rows || []).map((row) => row['Tên Hệ thống']))
        if (Number(saved?.removed_employee_count || 0) > 0) {
          setNotice({
            type: 'warning',
            message: `Đã loại ${saved.removed_employee_count} nhân viên đã xóa khỏi bảng lương nháp. Bạn có thể chỉnh sửa và lưu lại bình thường.`,
          })
        }
      })
      .catch((error) => {
        if (active) setNotice({ type: 'error', message: error.message })
      })
    return () => { active = false }
  }, [autoOpenLatestDraft, canCalculate, month, periodNo])

  const historyTotal = useMemo(() => history.records.reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [history.records])
  const historyRowKey = (item, index) => `${item['Mã bản lưu'] || ''}:${item['Tên Hệ thống'] || ''}:${index}`
  const historyKeys = history.records.map(historyRowKey)
  const allHistorySelected = historyKeys.length > 0 && historyKeys.every((key) => historySelected.includes(key))
  const draftTotal = useMemo(() => (draft?.rows || []).reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [draft])
  const draftSalaryTotal = useMemo(() => (draft?.rows || []).reduce((sum, item) => sum + Number(item['Tiền Lương'] || 0), 0), [draft])
  const draftRows = draft?.rows || []
  const draftNeedle = normalizeSearch(draftSearch)
  const visibleDraftRows = useMemo(() => draftRows.filter((row) => {
    if (draftNeedle && !searchTextMatches([row['Tên Hệ thống'], row['Họ và tên']], draftNeedle)) return false
    if (draftNonPositiveOnly && Number(row['Số tiền thực nhận'] || 0) > 0) return false
    if (draftFormerOnly && String(row.__employment_status || '').trim() !== 'Đã nghỉ việc') return false
    return true
  }), [draftRows, draftNeedle, draftNonPositiveOnly, draftFormerOnly])
  const visibleDraftSummary = useMemo(() => {
    const fields = [
      'Tiền Lương', 'Tiền Hỗ Trợ Hoàn Lại', 'Hoàn trả tiền tích lũy', 'Tích lũy',
      'Chi Phí Sinh Hoạt', 'Tiền phạt trong tháng', 'Vi phạm kỳ trước', 'Tiền ứng lương',
      'Tiền hỗ trợ Locker', 'Số tiền thực nhận',
    ]
    return Object.fromEntries(fields.map((field) => [
      field,
      visibleDraftRows.reduce((sum, row) => sum + Number(row[field] || 0), 0),
    ]))
  }, [visibleDraftRows])
  useEffect(() => {
    if (!draftNeedle) {
      setSearchSelectionMode(false)
      return
    }
    const names = visibleDraftRows.map((row) => row['Tên Hệ thống'])
    setSearchSelectionMode(true)
    setSelected(names.length === 1 ? names : [])
  }, [draftNeedle, visibleDraftRows])

  const isBusy = Boolean(busy)
  const allVisibleSelected = !searchSelectionMode
    && visibleDraftRows.length > 0
    && visibleDraftRows.every((row) => selected.includes(row['Tên Hệ thống']))

  const toggleAllSelected = () => {
    setSearchSelectionMode(false)
    const names = visibleDraftRows.map((row) => row['Tên Hệ thống'])
    setSelected((current) => {
      if (allVisibleSelected) return current.filter((name) => !names.includes(name))
      return Array.from(new Set([...current, ...names]))
    })
  }

  const calculate = () => run('calculate', async () => {
    const result = await veraApi.calculatePayrollFromTips(month, periodNo)
    setDraft(result)
    setDraftSearch('')
    setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
    setConfig(result.config || config); setConfigBaseline(JSON.stringify(result.config || config))
    const summary = result.source_summary || {}
    const detail = summary.matched_tip_rows
      ? `${summary.matched_tip_rows} dòng Tip · Tổng Tiền Lương ${money(summary.matched_salary_total)}`
      : ''
    const syncWarning = result.legacy_obligation_warning ? ` · ${result.legacy_obligation_warning}` : ''
    setNotice({
      type: result.unmatched?.length || syncWarning ? 'warning' : 'success',
      message: result.unmatched?.length
        ? `Đã tính ${result.period_label} · ${detail}. Chưa khớp tài khoản: ${result.unmatched.join(', ')}${syncWarning}`
        : `Đã tính ${result.period_label}${detail ? ` · ${detail}` : ''}${syncWarning}.`,
    })
  })

  const recalculatePayroll = () => run('recalculate', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương nháp để tính lại.')
    const result = await veraApi.calculatePayrollFromTips(month, periodNo)
    setDraft(result)
    setDraftSearch('')
    setSearchSelectionMode(false)
    setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
    setConfig(result.config || config); setConfigBaseline(JSON.stringify(result.config || config))
    const summary = result.source_summary || {}
    const detail = summary.matched_tip_rows
      ? `${summary.matched_tip_rows} dòng Tip · Tổng Tiền Lương ${money(summary.matched_salary_total)}`
      : ''
    const syncWarning = result.legacy_obligation_warning ? ` · ${result.legacy_obligation_warning}` : ''
    setNotice({
      type: result.unmatched?.length || syncWarning ? 'warning' : 'success',
      message: result.unmatched?.length
        ? `Đã tính lại ${result.period_label} · ${detail}. Chưa khớp tài khoản: ${result.unmatched.join(', ')}${syncWarning}`
        : `Đã tính lại ${result.period_label}${detail ? ` · ${detail}` : ''}${syncWarning}.`,
    })
  })

  const editMoney = (username, field, value) => {
    setDraft((current) => current ? ({
      ...current,
      saved_at: '',
      saved_by: '',
      rows: current.rows.map((row) => row['Tên Hệ thống'] === username
        ? recalculate({ ...row, [field]: Number(value || 0) }) : row),
    }) : current)
  }

  const saveDraftSnapshot = () => run('save-draft', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương nháp để lưu.')
    const result = await veraApi.savePayrollDraft({
      start: draft.start,
      end: draft.end,
      source_name: draft.source_name || 'TIP nhân viên từ Live Tour',
      rows: draft.rows,
    })
    setDraft(result.draft)
    setSelected((result.draft?.rows || []).map((row) => row['Tên Hệ thống']))
    setNotice({ type: 'success', message: result.message })
  })

  const deleteDraftSnapshot = () => run('delete-draft', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương nháp để xóa.')
    if (!window.confirm(`Xóa bảng lương nháp ${draft.period_label}?`)) return
    const result = await veraApi.deletePayrollDraft(month, periodNo)
    setDraft(null)
    setSelected([])
    setNotice({ type: 'success', message: result.message })
  })

  const completePayroll = () => run('complete', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương để hoàn thành.')
    if (draftSalaryTotal <= 0) throw new Error('Tổng Tiền Lương đang bằng 0. Không thể hoàn thành bảng lương.')
    if (!window.confirm(`Hoàn thành ${draft.period_label}? Bảng lương sẽ được lưu vào LỊCH SỬ BẢNG LƯƠNG.`)) return
    const result = await veraApi.savePayroll({
      start: draft.start,
      end: draft.end,
      source_name: draft.source_name || 'TIP nhân viên từ Live Tour',
      rows: draft.rows,
    })
    try { await veraApi.deletePayrollDraft(month, periodNo) } catch { /* official payroll is already saved */ }
    setDraft(null)
    setSelected([])
    setDraftSearch('')
    await Promise.all([loadHistory('', employee), loadSavedBatches(), loadSupporting()])
    setBatch('')
    setNotice({ type: 'success', message: result.message })
  })

  const deferPenalty = (row) => run(`defer-${row['Tên Hệ thống']}`, async () => {
    if (!draft?.start || !draft?.end) throw new Error('Chưa xác định được kỳ lương hiện tại.')
    const amount = Number(row['Tiền phạt trong tháng'] || 0)
    if (amount <= 0) throw new Error(`${row['Tên Hệ thống']} không có Vi phạm kỳ này để chuyển.`)
    if (!window.confirm(`Chuyển ${money(amount)} Vi phạm kỳ này của ${row['Tên Hệ thống']} sang kỳ lương kế tiếp?`)) return
    const result = await enhancementRequest('/v2/payroll/penalties/defer', {
      method: 'POST',
      body: JSON.stringify({
        employee_name: row['Tên Hệ thống'],
        amount,
        period_start: draft.start,
        period_end: draft.end,
      }),
    })
    const nextRows = draft.rows.map((item) => item['Tên Hệ thống'] === row['Tên Hệ thống']
      ? recalculate({ ...item, 'Tiền phạt trong tháng': 0 }) : item)
    const nextDraft = { ...draft, rows: nextRows, saved_at: '', saved_by: '' }
    setDraft(nextDraft)
    try {
      const saved = await veraApi.savePayrollDraft({
        start: draft.start,
        end: draft.end,
        source_name: draft.source_name || 'TIP nhân viên từ Live Tour',
        rows: nextRows,
      })
      setDraft(saved.draft)
    } catch (error) {
      setNotice({ type: 'warning', message: `${result.message} Tuy nhiên chưa lưu được bảng lương nháp: ${error.message}` })
      await loadSupporting()
      return
    }
    await loadSupporting()
    setNotice({ type: 'success', message: result.message })
  })

  const emailDraft = () => run('email', async () => {
    const rows = (draft?.rows || []).filter((row) => selected.includes(row['Tên Hệ thống']))
    if (!rows.length) throw new Error('Chưa chọn nhân viên cần gửi email.')
    if (!window.confirm(`Gửi bảng lương qua email cho ${rows.length} nhân viên đã chọn?`)) return

    const batchSize = 3
    const sent = []
    const failed = []
    setEmailProgress({ processed: 0, total: rows.length })
    try {
      for (let offset = 0; offset < rows.length; offset += batchSize) {
        const chunk = rows.slice(offset, offset + batchSize)
        let result
        try {
          result = await veraApi.emailPayroll({ start: draft.start, end: draft.end, rows: chunk })
        } catch (error) {
          throw new Error(
            `Đã xử lý xong ${offset}/${rows.length} nhân viên. Nhóm hiện tại đã dừng và không tự thử lại để tránh gửi email trùng. ${error.message}`,
          )
        }
        sent.push(...(result.sent || []))
        failed.push(...(result.failed || []))
        setEmailProgress({ processed: Math.min(offset + chunk.length, rows.length), total: rows.length })
      }
      const failedNames = failed.slice(0, 5).map((item) => item.employee).filter(Boolean).join(', ')
      const detail = failedNames ? ` · Lỗi: ${failedNames}${failed.length > 5 ? '…' : ''}` : ''
      setNotice({
        type: failed.length ? 'warning' : 'success',
        message: `Đã gửi ${sent.length}/${rows.length} email; lỗi ${failed.length}.${detail}`,
      })
    } finally {
      setEmailProgress(null)
    }
  })

  const exportDraft = () => run('export-draft', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương mới để xuất Excel.')
    await veraApi.exportPayrollDraft({ start: draft.start, end: draft.end, rows: draft.rows })
    setNotice({ type: 'success', message: `Đã Export to Excel: ${draft.period_label}.` })
  })

  const exportHistory = () => run('export-history', async () => {
    if (!history.records.length) throw new Error('Không có dữ liệu lịch sử phù hợp để xuất Excel.')
    await veraApi.exportPayrollExcel(batch, employee)
    setNotice({ type: 'success', message: 'Đã xuất Excel lịch sử bảng lương theo bộ lọc đang xem.' })
  })

  const reopenSavedPayroll = (batchId) => run(`reopen-${batchId}`, async () => {
    const result = await enhancementRequest(`/v2/payroll/saved-batches/${encodeURIComponent(batchId)}/edit`, { method: 'POST' })
    setAutoOpenLatestDraft(false)
    setMonth(String(result.month))
    setPeriodNo(Number(result.period_no))
    setDraft(result.draft)
    setDraftSearch('')
    setSelected((result.draft?.rows || []).map((row) => row['Tên Hệ thống']))
    onTabChange?.('calculate')
    setNotice({ type: 'success', message: result.message })
    window.setTimeout(() => document.querySelector('.payroll-page-enhanced .payroll-draft-panel')?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 120)
  })

  const emailHistory = () => run('email-history', async () => {
    const rows = history.records.filter((item, index) => historySelected.includes(historyRowKey(item, index)))
    if (!rows.length) throw new Error('Chưa chọn nhân viên trong lịch sử để gửi email.')
    if (!window.confirm(`Gửi bảng lương qua email cho ${rows.length} nhân viên đã chọn?`)) return
    const groups = new Map()
    rows.forEach((row) => {
      const key = `${row['Từ ngày'] || ''}|${row['Đến ngày'] || ''}`
      if (!groups.has(key)) groups.set(key, { start: row['Từ ngày'], end: row['Đến ngày'], rows: [] })
      groups.get(key).rows.push(row)
    })
    let processed = 0
    const sent = []
    const failed = []
    setEmailProgress({ processed: 0, total: rows.length })
    try {
      for (const group of groups.values()) {
        for (let offset = 0; offset < group.rows.length; offset += 3) {
          const chunk = group.rows.slice(offset, offset + 3)
          let result
          try {
            result = await veraApi.emailPayroll({ start: group.start, end: group.end, rows: chunk })
          } catch (error) {
            throw new Error(`Đã xử lý xong ${processed}/${rows.length} nhân viên. Nhóm hiện tại đã dừng và không tự thử lại để tránh gửi email trùng. ${error.message}`)
          }
          sent.push(...(result.sent || []))
          failed.push(...(result.failed || []))
          processed += chunk.length
          setEmailProgress({ processed, total: rows.length })
        }
      }
      setNotice({ type: failed.length ? 'warning' : 'success', message: `Đã gửi ${sent.length}/${rows.length} email; lỗi ${failed.length}.` })
    } finally {
      setEmailProgress(null)
    }
  })

  const saveConfig = () => run('config', async () => {
    const result = await veraApi.savePayrollConfig(config)
    setConfig(result.config); setConfigBaseline(JSON.stringify(result.config))
    setNotice({ type: 'success', message: result.message })
  })

  const addAccumulationRefund = (event) => {
    event.preventDefault()
    void run('accumulation-refund', async () => {
      const dates = periodDates(month, periodNo)
      const result = await veraApi.createPayrollAccumulationRefund({
        ...refundForm,
        amount: Number(refundForm.amount),
        start: dates.start,
        end: dates.end,
      })
      setAccumulationRefunds((current) => [
        ...current.filter((item) => item.id !== result.refund.id),
        result.refund,
      ])
      setRefundForm({ employee_name: '', amount: '', note: 'Hoàn trả tiền tích lũy khi nghỉ việc' })
      setNotice({ type: 'success', message: `${result.message} Hãy bấm Tính lại lương để áp dụng vào bảng nháp.` })
    })
  }

  const removeAccumulationRefund = (id) => run(`accumulation-refund-${id}`, async () => {
    if (!window.confirm('Xóa cài đặt hoàn trả tiền tích lũy này?')) return
    const result = await veraApi.deletePayrollAccumulationRefund(id)
    setAccumulationRefunds((current) => current.filter((item) => item.id !== id))
    setNotice({ type: 'success', message: `${result.message} Hãy bấm Tính lại lương nếu bảng nháp đã được tạo.` })
  })

  const addObligation = (event) => {
    event.preventDefault()
    void run('obligation', async () => {
      const result = await veraApi.createPayrollObligation({ ...obligationForm, amount: Number(obligationForm.amount) })
      setObligations((current) => [...current, result.obligation])
      setObligationForm({ employee_name: '', amount: '', content: 'Chưa hoàn thành nghĩa vụ Vi phạm', due_from: '' })
      await loadSupporting()
      setNotice({ type: 'success', message: result.message })
    })
  }

  const removeObligation = (id) => run(`obligation-${id}`, async () => {
    if (!window.confirm('Xóa Nghĩa vụ vi phạm này?')) return
    const result = await veraApi.deletePayrollObligation(id)
    setObligations((current) => current.filter((item) => item.id !== id))
    await loadSupporting()
    setNotice({ type: 'success', message: result.message })
  })

  const syncLegacy = () => run('sync-legacy', async () => {
    if (!window.confirm('Tải lại lịch sử bảng lương và Nghĩa vụ vi phạm từ hệ thống cũ? Dữ liệu Web V2 đã lưu vẫn được ưu tiên hiển thị.')) return
    const result = await veraApi.syncLegacyPayroll()
    await Promise.all([loadHistory(), loadSavedBatches(), loadSupporting()])
    setNotice({ type: 'success', message: result.message })
  })

  const deleteHistoryBatch = (batchId) => run(`delete-history-${batchId}`, async () => {
    if (!batchId) throw new Error('Vui lòng chọn kỳ lương cần xóa.')
    if (!window.confirm(`Xóa lịch sử bảng lương “${batchId}”? Hành động này chỉ dành cho Admin/quyền quản lý lịch sử.`)) return
    const result = await enhancementRequest(`/v2/payroll/history/${encodeURIComponent(batchId)}`, { method: 'DELETE' })
    const nextBatch = batch === batchId ? '' : batch
    if (batch === batchId) setBatch('')
    await Promise.all([loadHistory(nextBatch, employee), loadSavedBatches()])
    setNotice({ type: 'success', message: result.message })
  })

  return <div className={`feature-page payroll-page payroll-page-enhanced payroll-tab-${activeTab}`}>
    <div data-ui-key="u-4dcec71791b4" className="page-heading"><div><span className="eyebrow"><WalletCards size={14} /> Kỳ 1 · Kỳ 2</span><h1>BẢNG LƯƠNG</h1><p>Tính lương trực tiếp từ tiền TIP nhân viên, quản lý khấu trừ, hoàn thành và lưu lịch sử bảng lương.</p></div><button data-ui-key="u-c2ca30d80853" data-ui-label-default="Làm mới" className="secondary-button" onClick={reload} disabled={isBusy}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /><UiCustomText uiKey="u-c2ca30d80853"> Làm mới</UiCustomText></button></div>
    <UiToolbar data-ui-key="u-a39c42009c7e" className="payroll-main-tabs" role="tablist" aria-label="Lương KTV">
      <button data-ui-key="u-6a99f7168de5" data-ui-label-default="Tính lương" type="button" role="tab" aria-selected={activeTab === 'calculate'} className={activeTab === 'calculate' ? 'active' : ''} onClick={() => onTabChange?.('calculate')}><UiCustomText uiKey="u-6a99f7168de5">Tính lương</UiCustomText></button>
      <button data-ui-key="u-5f140dee458d" data-ui-label-default="Lịch sử bảng lương" type="button" role="tab" aria-selected={activeTab === 'history'} className={activeTab === 'history' ? 'active' : ''} onClick={() => onTabChange?.('history')}><UiCustomText uiKey="u-5f140dee458d">Lịch sử bảng lương</UiCustomText></button>
    </UiToolbar>
    <StableFeedback>{notice && <div className={notice.type === 'error' ? 'error-box' : notice.type === 'warning' ? 'warning-box' : 'success-box'}>{notice.message}</div>}</StableFeedback>

    {canCalculate && <section data-ui-key="u-856731095818" className="panel payroll-calculate-panel">
      <div data-ui-key="u-7722410132ee" className="panel-title-row"><div><h2>TÍNH BẢNG LƯƠNG</h2><p>Kỳ 1 là 01–15; Kỳ 2 là 16–cuối tháng. Nợ vi phạm đủ ngày bắt đầu trừ sẽ tự cộng vào “Nợ vi phạm kỳ trước”.</p></div></div>
      <UiToolbar data-ui-key="u-8d0f10645723" className="data-toolbar">
        <label>Tháng lương<input type="month" value={month} disabled={isBusy} onChange={(event) => { setAutoOpenLatestDraft(false); setMonth(event.target.value) }} /></label>
        <label>Kỳ lương<select value={periodNo} disabled={isBusy} onChange={(event) => { setAutoOpenLatestDraft(false); setPeriodNo(Number(event.target.value)) }}><option value={1}>Kỳ 1</option><option value={2}>Kỳ 2</option></select></label>
        <button data-ui-key="u-fa0f02dfbb3f" className="primary-button" onClick={calculate} disabled={isBusy}><WalletCards size={16} /> {busy === 'calculate' ? 'Đang tính…' : 'Tính lương từ TIP'}</button>
      </UiToolbar>
      <UiToolbar data-ui-key="u-d77fe86a944d" className="payroll-draft-toolbar">
        <div><strong>BẢNG LƯƠNG NHÁP</strong><small>{draft?.rows?.length ? `${draft.period_label} · ${draft.rows.length} nhân viên${draft.saved_at ? ` · Đã lưu bởi ${draft.saved_by}` : ' · Chưa lưu trên máy chủ'}` : 'Chưa có dữ liệu nháp cho kỳ đang chọn.'}</small></div>
        <UiToolbar data-ui-key="u-e897f7d9f0d6" className="list-actions">
          <button data-ui-key="u-67cfa949cbc8" className="secondary-button" type="button" onClick={recalculatePayroll} disabled={isBusy || !draftRows.length}><RefreshCw size={16} className={busy === 'recalculate' ? 'spin' : ''} /> {busy === 'recalculate' ? 'Đang tính lại…' : 'Tính lại lương'}</button>
          {canExport && <button data-ui-key="u-44591d8d625e" className="secondary-button" type="button" onClick={exportDraft} disabled={isBusy || !draftRows.length}><Download size={16} /> {busy === 'export-draft' ? 'Đang Export…' : 'Export to Excel'}</button>}
          {canSave && <button data-ui-key="u-ce81fd2f3ea0" className="secondary-button" type="button" onClick={saveDraftSnapshot} disabled={isBusy || !draftRows.length}><Save size={16} /> {busy === 'save-draft' ? 'Đang lưu…' : 'Lưu bảng lương nháp'}</button>}
          {canSave && <button data-ui-key="u-7f80b2224b32" className="danger-button" type="button" onClick={deleteDraftSnapshot} disabled={isBusy || !draftRows.length}><Trash2 size={16} /> {busy === 'delete-draft' ? 'Đang xóa…' : 'Xóa bảng lương nháp'}</button>}
        </UiToolbar>
      </UiToolbar>
    </section>}

    {draft?.rows?.length > 0 && <section data-ui-key="u-b5130dabd90f" className="panel payroll-draft-panel">
      <div data-ui-key="u-1fea30877196" className="panel-title-row"><div><h2>{draft.period_label}</h2><p>{draft.rows.length} nhân viên · Tổng Tiền Lương {money(draftSalaryTotal)} · Tổng thực nhận {money(draftTotal)}</p></div><UiToolbar data-ui-key="u-62395aec935b" className="list-actions">{canSave && <button data-ui-key="u-ffb464f0cbcc" className="primary-button" onClick={completePayroll} disabled={isBusy || draftSalaryTotal <= 0}><CheckCircle2 size={16} /> {busy === 'complete' ? 'Đang hoàn thành…' : 'Hoàn thành bảng lương'}</button>}{canEmail && <button data-ui-key="u-83cf7f0e45eb" className="secondary-button" onClick={emailDraft} disabled={isBusy}><Mail size={16} /> {busy === 'email' && emailProgress ? `Đang gửi ${emailProgress.processed}/${emailProgress.total}…` : `Gửi email (${selected.length})`}</button>}</UiToolbar></div>
      <UiToolbar data-ui-key="u-4f690860c619" className="payroll-search-toolbar">
        <label className="payroll-search-box">Tìm tên nhân viên<Search size={16} /><ClearableSearchInput type="search" value={draftSearch} disabled={isBusy} placeholder={`Tìm trong ${draft.period_label}`} onChange={(event) => setDraftSearch(event.target.value)} /></label>
        <UiToolbar data-ui-key="u-879165f77c07" className="payroll-quick-filters">
          <button data-ui-key="u-be78236f911a" data-ui-label-default="Thực nhận ≤ 0" type="button" className={`secondary-button ${draftNonPositiveOnly ? 'active-filter' : ''}`} onClick={() => setDraftNonPositiveOnly((value) => !value)} disabled={isBusy}><UiCustomText uiKey="u-be78236f911a">Thực nhận ≤ 0</UiCustomText></button>
          <button data-ui-key="u-63547a06487b" data-ui-label-default="Đã nghỉ việc" type="button" className={`secondary-button ${draftFormerOnly ? 'active-filter' : ''}`} onClick={() => setDraftFormerOnly((value) => !value)} disabled={isBusy}><UiCustomText uiKey="u-63547a06487b">Đã nghỉ việc</UiCustomText></button>
          {(draftNonPositiveOnly || draftFormerOnly || draftSearch) && <button data-ui-key="u-7dd3f7dc9f42" data-ui-label-default="Xóa lọc" type="button" className="secondary-button" onClick={() => { setDraftSearch(''); setDraftNonPositiveOnly(false); setDraftFormerOnly(false) }} disabled={isBusy}><UiCustomText uiKey="u-7dd3f7dc9f42">Xóa lọc</UiCustomText></button>}
        </UiToolbar>
        <div><strong>Hiển thị {visibleDraftRows.length}/{draftRows.length} nhân viên</strong></div>
      </UiToolbar>
      {canEmail && <label className="payroll-select-all"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAllSelected} disabled={isBusy || !visibleDraftRows.length} /> Chọn tất cả nhân viên đang hiển thị để gửi email</label>}
      <div className="payroll-column-summary" aria-label="Tổng các cột bảng lương đang hiển thị">
        <div><span>Lương</span><strong>{money(visibleDraftSummary['Tiền Lương'])}</strong></div>
        <div><span>Trách nhiệm / hỗ trợ</span><strong>{money(visibleDraftSummary['Tiền Hỗ Trợ Hoàn Lại'])}</strong></div>
        <div><span>Hoàn trả tích lũy</span><strong>{money(visibleDraftSummary['Hoàn trả tiền tích lũy'])}</strong></div>
        <div><span>Tích lũy</span><strong>{money(visibleDraftSummary['Tích lũy'])}</strong></div>
        <div><span>Phí sinh hoạt</span><strong>{money(visibleDraftSummary['Chi Phí Sinh Hoạt'])}</strong></div>
        <div><span>Vi phạm kỳ này</span><strong>{money(visibleDraftSummary['Tiền phạt trong tháng'])}</strong></div>
        <div><span>Nợ vi phạm kỳ trước</span><strong>{money(visibleDraftSummary['Vi phạm kỳ trước'])}</strong></div>
        <div><span>Tiền ứng</span><strong>{money(visibleDraftSummary['Tiền ứng lương'])}</strong></div>
        <div><span>Hỗ trợ Locker</span><strong>{money(visibleDraftSummary['Tiền hỗ trợ Locker'])}</strong></div>
        <div><span>Thực nhận</span><strong>{money(visibleDraftSummary['Số tiền thực nhận'])}</strong></div>
      </div>
      <div className="responsive-data-table payroll-editor payroll-desktop-table payroll-fit-table"><table data-ui-key="u-b0f2bdeed291"><thead><tr>{canEmail && <th data-ui-key="u-642a2704e611" data-ui-label-default="Gửi"><UiCustomText uiKey="u-642a2704e611">Gửi</UiCustomText></th>}<th data-ui-key="u-207ee9a98e45" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-207ee9a98e45">Nhân viên</UiCustomText></th><th data-ui-key="u-8e2d4fb93173" data-ui-label-default="Lương"><UiCustomText uiKey="u-8e2d4fb93173">Lương</UiCustomText></th>{Object.entries(EDIT_LABELS).map(([field, label]) => <th data-ui-key="u-613edd6b3814" key={field}>{label}</th>)}<th data-ui-key="u-76f0a3456322" data-ui-label-default="Thực nhận"><UiCustomText uiKey="u-76f0a3456322">Thực nhận</UiCustomText></th></tr></thead><tbody>{visibleDraftRows.map((row) => <tr className={isNonPositive(row) ? 'payroll-nonpositive' : ''} key={row['Tên Hệ thống']}>{canEmail && <td className="center"><input type="checkbox" aria-label={`Chọn gửi email cho ${row['Tên Hệ thống']}`} checked={selected.includes(row['Tên Hệ thống'])} disabled={isBusy} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} /></td>}<td><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']}</small><small>{row.Email || 'Chưa có email'}</small></td><td className="money-cell">{money(row['Tiền Lương'])}</td>{Object.keys(EDIT_LABELS).map((field) => <td key={field}><UiToolbar data-ui-key="u-7c214079e7b7" className="payroll-cell-actions"><VeraMoneyInput className="payroll-money-input" disabled={isBusy} value={row[field]} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} />{field === 'Vi phạm kỳ trước' && <small>Đối trừ công nợ khi hoàn thành</small>}{field === 'Tiền phạt trong tháng' && canManageObligations && Number(row[field] || 0) > 0 && <button data-ui-key="u-5f85f55a1ba2" data-ui-label-default="Chuyển kỳ sau" type="button" className="secondary-button compact payroll-defer-button" disabled={isBusy} onClick={() => deferPenalty(row)}><ArrowRightCircle size={13} /><UiCustomText uiKey="u-5f85f55a1ba2"> Chuyển kỳ sau</UiCustomText></button>}</UiToolbar></td>)}<td className="money-cell"><strong>{money(row['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
      <div className="payroll-mobile-list">{visibleDraftRows.map((row) => <article className={`payroll-mobile-card${isNonPositive(row) ? ' payroll-nonpositive' : ''}`} key={row['Tên Hệ thống']}>
        <header className="payroll-mobile-head"><div className="payroll-mobile-person">{canEmail && <input type="checkbox" checked={selected.includes(row['Tên Hệ thống'])} disabled={isBusy} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} />}<div><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']} · {row.Email || 'Chưa có email'}</small></div></div><span><small>Thực nhận</small><strong>{money(row['Số tiền thực nhận'])}</strong></span></header>
        <div className="payroll-mobile-summary"><span>Lương<strong>{money(row['Tiền Lương'])}</strong></span><span>Tổng khấu trừ<strong>{money(Number(row['Tích lũy'] || 0) + Number(row['Chi Phí Sinh Hoạt'] || 0) + Number(row['Tiền phạt trong tháng'] || 0) + Number(row['Vi phạm kỳ trước'] || 0) + Number(row['Tiền ứng lương'] || 0) + Number(row['Tiền hỗ trợ Locker'] || 0))}</strong></span></div>
        {canManageObligations && Number(row['Tiền phạt trong tháng'] || 0) > 0 && <button data-ui-key="u-23ccd1032581" data-ui-label-default="Chuyển Vi phạm kỳ này sang kỳ sau" type="button" className="secondary-button" disabled={isBusy} onClick={() => deferPenalty(row)}><ArrowRightCircle size={15} /><UiCustomText uiKey="u-23ccd1032581"> Chuyển Vi phạm kỳ này sang kỳ sau</UiCustomText></button>}
        <details className="payroll-mobile-details"><summary>Điều chỉnh các khoản lương</summary><div className="payroll-mobile-edit-grid">{Object.entries(EDIT_LABELS).map(([field, label]) => <label key={field}>{label}<VeraMoneyInput disabled={isBusy} value={row[field]} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} /></label>)}</div></details>
      </article>)}</div>
      {!visibleDraftRows.length && <div className="setup-note">Không tìm thấy nhân viên phù hợp.</div>}
    </section>}

    {canManageObligations && <section data-ui-key="u-ee60725600e2" className="panel">
      <div data-ui-key="u-a2e96dc0ba72" className="panel-title-row"><div><h2>NGHĨA VỤ VI PHẠM</h2><p>Khoản còn mở sẽ tự đưa vào “Nợ vi phạm kỳ trước” khi đến ngày bắt đầu trừ. Vi phạm được Admin chuyển kỳ sẽ xuất hiện ở đây.</p></div></div>
      <div className="payroll-obligation-groups">{obligationGroups.map((group) => <ObligationGroup key={group.type} group={group} />)}</div>
      <form className="payroll-obligation-form" onSubmit={addObligation}><label>Nhân viên<input required list="payroll-employee-options" disabled={isBusy} value={obligationForm.employee_name} onChange={(event) => setObligationForm({ ...obligationForm, employee_name: event.target.value })} /></label><label>Số tiền<VeraMoneyInput required disabled={isBusy} value={obligationForm.amount} onChange={(event) => setObligationForm({ ...obligationForm, amount: event.target.value })} /></label><label>Bắt đầu trừ từ<VeraDateInput required aria-label="Bắt đầu trừ từ" disabled={isBusy} value={obligationForm.due_from} onChange={(event) => setObligationForm({ ...obligationForm, due_from: event.target.value })} /></label><label>Nội dung<input required disabled={isBusy} value={obligationForm.content} onChange={(event) => setObligationForm({ ...obligationForm, content: event.target.value })} /></label><button data-ui-key="u-ef6cecfbc3c8" data-ui-label-default="Thêm nghĩa vụ" className="primary-button" disabled={isBusy}><Plus size={16} /><UiCustomText uiKey="u-ef6cecfbc3c8"> Thêm nghĩa vụ</UiCustomText></button></form>
      <datalist id="payroll-employee-options">{Array.from(new Set([...(history.employees || []), ...draftRows.map((row) => row['Tên Hệ thống'])])).map((name) => <option key={name}>{name}</option>)}</datalist>
      <div className="responsive-data-table"><table data-ui-key="u-88b22ce94dc4"><thead><tr><th data-ui-key="u-c41b23c731b8" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-c41b23c731b8">Nhân viên</UiCustomText></th><th data-ui-key="u-c137193f9c1f" data-ui-label-default="Số tiền"><UiCustomText uiKey="u-c137193f9c1f">Số tiền</UiCustomText></th><th data-ui-key="u-a0b622925d7b" data-ui-label-default="Bắt đầu trừ"><UiCustomText uiKey="u-a0b622925d7b">Bắt đầu trừ</UiCustomText></th><th data-ui-key="u-f61aa83079f9" data-ui-label-default="Nội dung"><UiCustomText uiKey="u-f61aa83079f9">Nội dung</UiCustomText></th><th data-ui-key="u-3e6cecc0cf08"></th></tr></thead><tbody>{obligations.map((item) => <tr key={item.id}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.due_from}</td><td>{item.content}</td><td><button data-ui-key="u-70d68318aba0" data-ui-label-default="Xóa" className="danger-button compact" disabled={isBusy} onClick={() => removeObligation(item.id)}><Trash2 size={14} /><UiCustomText uiKey="u-70d68318aba0"> Xóa</UiCustomText></button></td></tr>)}</tbody></table></div>
      {!obligations.length && <div className="setup-note">Chưa có Nghĩa vụ vi phạm nhập/chuyển từ Web V2.</div>}
    </section>}

    <section data-ui-key="u-338c2d7b398f" className="panel payroll-history-panel">
      <div data-ui-key="u-9d1f05fd02a2" className="panel-title-row"><div><h2>LỊCH SỬ BẢNG LƯƠNG</h2><p>Danh sách các bảng lương đã hoàn thành và bộ lọc chi tiết từng nhân viên.</p></div>{canSyncLegacy && <button data-ui-key="u-77711be61991" className="secondary-button" onClick={syncLegacy} disabled={isBusy}><RefreshCw size={16} className={busy === 'sync-legacy' ? 'spin' : ''} /> {busy === 'sync-legacy' ? 'Đang tải…' : 'Tải dữ liệu hệ thống cũ'}</button>}</div>

      <div className="saved-payroll-list">{savedBatches.map((item) => <article className="saved-payroll-card" key={item.batch}><header><div><h3>{item.batch}</h3><small>{item.saved_date ? `Lưu ${item.saved_date}${item.saved_time ? ` · ${item.saved_time}` : ''}` : 'Bảng lương đã lưu'}</small></div><UiToolbar data-ui-key="u-22eced718015" className="list-actions">{canSyncLegacy && <button data-ui-key="u-39395c5de662" className="secondary-button compact" type="button" disabled={isBusy} onClick={() => reopenSavedPayroll(item.batch)}><Edit3 size={14} /> {busy === `reopen-${item.batch}` ? 'Đang mở…' : 'Sửa bảng lương'}</button>}{canDeleteHistory && <button data-ui-key="u-f850fb1d74d2" data-ui-label-default="Xóa" className="danger-button compact" type="button" disabled={isBusy} onClick={() => deleteHistoryBatch(item.batch)}><Trash2 size={14} /><UiCustomText uiKey="u-f850fb1d74d2"> Xóa</UiCustomText></button>}</UiToolbar></header><div className="saved-payroll-metrics"><span>Nhân viên<strong>{item.employee_count}</strong></span><span>Tổng thực nhận<strong>{money(item.total_net)}</strong></span></div><button data-ui-key="u-c94c425924b5" data-ui-label-default="Xem chi tiết" className="secondary-button" type="button" disabled={isBusy} onClick={() => setBatch(item.batch)}><UiCustomText uiKey="u-c94c425924b5">Xem chi tiết</UiCustomText></button></article>)}</div>
      {!savedBatches.length && <div className="setup-note">Chưa có bảng lương đã hoàn thành.</div>}

      <UiToolbar data-ui-key="u-f20b1fef821b" className="data-toolbar history-delete-actions"><label>Kỳ lương<select value={batch} disabled={isBusy} onChange={(event) => setBatch(event.target.value)}><option value="">Tất cả kỳ lương</option>{history.batches.map((item) => <option key={item}>{item}</option>)}</select></label><label>Nhân viên<select value={employee} disabled={isBusy} onChange={(event) => setEmployee(event.target.value)}><option value="">Tất cả nhân viên</option>{history.employees.map((item) => <option key={item}>{item}</option>)}</select></label>{canExport && <button data-ui-key="u-e9ca5a611292" className="secondary-button" onClick={exportHistory} disabled={isBusy}><Download size={16} /> {busy === 'export-history' ? 'Đang xuất…' : 'Excel lịch sử'}</button>}{canEmail && <button data-ui-key="u-51881dff155c" className="secondary-button" type="button" onClick={emailHistory} disabled={isBusy || !historySelected.length}><Mail size={16} /> {busy === 'email-history' && emailProgress ? `Đang gửi ${emailProgress.processed}/${emailProgress.total}…` : `Gửi email (${historySelected.length})`}</button>}{canDeleteHistory && <button data-ui-key="u-9839d630c477" data-ui-label-default="Xóa lịch sử kỳ đang chọn" className="danger-button" type="button" disabled={isBusy || !batch} onClick={() => deleteHistoryBatch(batch)}><Trash2 size={16} /><UiCustomText uiKey="u-9839d630c477"> Xóa lịch sử kỳ đang chọn</UiCustomText></button>}</UiToolbar>
      {canEmail && <label className="payroll-select-all"><input type="checkbox" checked={allHistorySelected} onChange={() => setHistorySelected(allHistorySelected ? [] : historyKeys)} disabled={isBusy || !historyKeys.length} /> Chọn tất cả nhân viên đang hiển thị để gửi email</label>}
      <div className="metric-grid small payroll-history-metrics"><div data-ui-key="u-1afe5bbd851b" className="metric-card"><span>Số dòng lương</span><strong>{history.records.length}</strong></div><div data-ui-key="u-66c0bdee3dce" className="metric-card"><span>Tổng thực nhận đang xem</span><strong>{money(historyTotal)}</strong></div></div>
      <div className="responsive-data-table payroll-history-desktop"><table data-ui-key="u-a10738a2726e"><thead><tr>{canEmail && <th data-ui-key="u-ee2d2926335e" data-ui-label-default="Gửi"><UiCustomText uiKey="u-ee2d2926335e">Gửi</UiCustomText></th>}<th data-ui-key="u-97fe3fec6da3" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-97fe3fec6da3">Nhân viên</UiCustomText></th><th data-ui-key="u-1e5c8ae68f44" data-ui-label-default="Kỳ lương"><UiCustomText uiKey="u-1e5c8ae68f44">Kỳ lương</UiCustomText></th><th data-ui-key="u-0a896f53f4a8" data-ui-label-default="Lương"><UiCustomText uiKey="u-0a896f53f4a8">Lương</UiCustomText></th><th data-ui-key="u-4327b0bada56" data-ui-label-default="Hoàn trả tích lũy"><UiCustomText uiKey="u-4327b0bada56">Hoàn trả tích lũy</UiCustomText></th><th data-ui-key="u-a0044d60bbc9" data-ui-label-default="Vi phạm"><UiCustomText uiKey="u-a0044d60bbc9">Vi phạm</UiCustomText></th><th data-ui-key="u-d3d04e4c6dd6" data-ui-label-default="Nợ vi phạm kỳ trước"><UiCustomText uiKey="u-d3d04e4c6dd6">Nợ vi phạm kỳ trước</UiCustomText></th><th data-ui-key="u-e546dcbd270f" data-ui-label-default="Thực nhận"><UiCustomText uiKey="u-e546dcbd270f">Thực nhận</UiCustomText></th></tr></thead><tbody>{history.records.map((item, index) => { const rowKey = historyRowKey(item, index); return <tr className={isNonPositive(item) ? 'payroll-nonpositive' : ''} key={rowKey}>{canEmail && <td className="center"><input type="checkbox" aria-label={`Chọn gửi email cho ${item['Tên Hệ thống']}`} checked={historySelected.includes(rowKey)} disabled={isBusy} onChange={() => setHistorySelected((current) => current.includes(rowKey) ? current.filter((key) => key !== rowKey) : [...current, rowKey])} /></td>}<td><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small><small>{item.Email || 'Chưa có email'}</small></td><td>{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</td><td>{money(item['Tiền Lương'])}</td><td>{money(item['Hoàn trả tiền tích lũy'])}</td><td>{money(item['Tiền phạt trong tháng'])}</td><td>{money(item['Vi phạm kỳ trước'])}</td><td><strong>{money(item['Số tiền thực nhận'])}</strong></td></tr> })}</tbody></table></div>
      <div className="payroll-mobile-list payroll-history-mobile">{history.records.map((item, index) => { const rowKey = historyRowKey(item, index); return <article className={`payroll-mobile-card${isNonPositive(item) ? ' payroll-nonpositive' : ''}`} key={rowKey}><header className="payroll-mobile-head"><div className="payroll-mobile-person">{canEmail && <input type="checkbox" aria-label={`Chọn gửi email cho ${item['Tên Hệ thống']}`} checked={historySelected.includes(rowKey)} disabled={isBusy} onChange={() => setHistorySelected((current) => current.includes(rowKey) ? current.filter((key) => key !== rowKey) : [...current, rowKey])} />}<div><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']} · {item.Email || 'Chưa có email'}</small></div></div><span><small>Thực nhận</small><strong>{money(item['Số tiền thực nhận'])}</strong></span></header><strong className="payroll-mobile-period">{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</strong><div className="payroll-mobile-summary payroll-history-summary"><span>Lương<strong>{money(item['Tiền Lương'])}</strong></span><span>Hoàn trả tích lũy<strong>{money(item['Hoàn trả tiền tích lũy'])}</strong></span><span>Vi phạm<strong>{money(item['Tiền phạt trong tháng'])}</strong></span><span>Nợ cũ<strong>{money(item['Vi phạm kỳ trước'])}</strong></span></div></article> })}</div>
      {!history.records.length && <div className="setup-note">Không có bảng lương phù hợp.</div>}
    </section>

    {canEditConfig && <section data-ui-key="u-6d5ef6daf882" className="panel payroll-default-config-panel">
      <div data-ui-key="u-238aac3ce39b" className="panel-title-row"><div><h2><Settings2 size={17} /> CÀI ĐẶT KHẤU TRỪ MẶC ĐỊNH</h2><p>Đã chuyển xuống dưới LỊCH SỬ BẢNG LƯƠNG. Các mức này áp dụng khi tính bảng lương mới.</p></div><button data-ui-key="u-1fc73aabf48a" data-ui-label-default="Lưu cài đặt" className="primary-button" onClick={saveConfig} disabled={isBusy}><Save size={16} /><UiCustomText uiKey="u-1fc73aabf48a"> Lưu cài đặt</UiCustomText></button></div>
      <div className="payroll-config-grid">
        <label>Chi phí sinh hoạt<VeraMoneyInput disabled={isBusy} value={config.default_living_expense} onChange={(event) => setConfig({ ...config, default_living_expense: Number(event.target.value) })} /></label>
        <label>Hỗ trợ Locker<VeraMoneyInput disabled={isBusy} value={config.default_locker_support} onChange={(event) => setConfig({ ...config, default_locker_support: Number(event.target.value) })} /></label>
        <label>Tiền trách nhiệm Leader (Kỳ 2)<VeraMoneyInput disabled={isBusy} value={config.leader_responsibility_allowance} onChange={(event) => setConfig({ ...config, leader_responsibility_allowance: Number(event.target.value) })} /></label>
      </div>
    </section>}

    {isAdmin && canEditConfig && <section data-ui-key="u-5e001ef9c559" className="panel payroll-accumulation-refund-panel">
      <div data-ui-key="u-ca54a8269f5a" className="panel-title-row"><div><h2>HOÀN TRẢ TIỀN TÍCH LŨY – NHÂN VIÊN NGHỈ VIỆC</h2><p>Admin nhập thủ công; khoản hoàn trả được cộng đúng vào kỳ đang chọn và không khấu trừ Tích lũy thêm trong kỳ đó.</p></div></div>
      <form className="payroll-refund-form" onSubmit={addAccumulationRefund}>
        <label>Nhân viên nghỉ việc<select required disabled={isBusy} value={refundForm.employee_name} onChange={(event) => setRefundForm({ ...refundForm, employee_name: event.target.value })}><option value="">-- Chọn nhân viên --</option>{formerEmployees.map((item) => <option key={item.employee_name} value={item.employee_name}>{item.employee_name} · {item.employment_status}</option>)}</select></label>
        <label>Số tiền hoàn trả<VeraMoneyInput required disabled={isBusy} value={refundForm.amount} onChange={(event) => setRefundForm({ ...refundForm, amount: event.target.value })} /></label>
        <label>Kỳ áp dụng<input readOnly value={`Kỳ ${periodNo} - Tháng ${Number(month.slice(5))}/${month.slice(0, 4)}`} /></label>
        <label>Ghi chú<input required disabled={isBusy} value={refundForm.note} onChange={(event) => setRefundForm({ ...refundForm, note: event.target.value })} /></label>
        <button data-ui-key="u-f13f9df7891c" data-ui-label-default="Lưu hoàn trả" className="primary-button" disabled={isBusy || !formerEmployees.length}><Plus size={16} /><UiCustomText uiKey="u-f13f9df7891c"> Lưu hoàn trả</UiCustomText></button>
      </form>
      <div className="responsive-data-table payroll-setting-table"><table data-ui-key="u-5e626342f477"><thead><tr><th data-ui-key="u-45edeaaeb45a" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-45edeaaeb45a">Nhân viên</UiCustomText></th><th data-ui-key="u-05074d7af8ac" data-ui-label-default="Số tiền"><UiCustomText uiKey="u-05074d7af8ac">Số tiền</UiCustomText></th><th data-ui-key="u-5f3f8bdc9bb5" data-ui-label-default="Kỳ áp dụng"><UiCustomText uiKey="u-5f3f8bdc9bb5">Kỳ áp dụng</UiCustomText></th><th data-ui-key="u-a44294fb2bcd" data-ui-label-default="Ghi chú"><UiCustomText uiKey="u-a44294fb2bcd">Ghi chú</UiCustomText></th><th data-ui-key="u-b53e5e7ab290"></th></tr></thead><tbody>{accumulationRefunds.map((item) => <tr key={item.id}><td><strong>{item.employee_name}</strong></td><td>{money(item.amount)}</td><td>{item.period_label || `${item.start} – ${item.end}`}</td><td>{item.note}</td><td><button data-ui-key="u-7dba73d76d99" data-ui-label-default="Xóa" type="button" className="danger-button compact" disabled={isBusy} onClick={() => removeAccumulationRefund(item.id)}><Trash2 size={14} /><UiCustomText uiKey="u-7dba73d76d99"> Xóa</UiCustomText></button></td></tr>)}</tbody></table></div>
      {!formerEmployees.length && <div className="setup-note">Chưa có nhân viên ở trạng thái Tạm thời nghỉ việc hoặc Đã nghỉ việc.</div>}
      {!accumulationRefunds.length && <div className="setup-note">Chưa có khoản hoàn trả tích lũy được cài đặt.</div>}
    </section>}
  </div>
}
