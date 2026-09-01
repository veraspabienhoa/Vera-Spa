import { ArrowRightCircle, CheckCircle2, Download, Mail, Plus, RefreshCw, Save, Search, Settings2, Trash2, Upload, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import { numberInputDisplayValue } from '../lib/numberInput'
import { getCurrentSession } from '../lib/supabase'
import './PayrollPageEnhanced.css'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const currentMonth = () => {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}
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
    <div className="responsive-data-table"><table><thead><tr><th>Tên nhân viên</th><th>{isNegative ? 'Tổng còn nợ' : 'Tổng tạm hoãn'}</th><th>{isNegative ? 'Số kỳ còn nợ' : 'Số kỳ tạm hoãn'}</th><th>{isNegative ? 'Kỳ nợ gần nhất' : 'Kỳ tạm hoãn gần nhất'}</th><th>Bắt đầu trừ từ</th></tr></thead><tbody>{summary.map((item) => <tr key={`${group.type}-${item.employee_name}`}><td>{item.employee_name}</td><td>{money(item.total)}</td><td className="center">{item.period_count}</td><td>{item.latest_period}</td><td>{item.due_from}</td></tr>)}</tbody></table></div>
    {!summary.length && <div className="setup-note">Không có khoản đang mở.</div>}
    {details.length > 0 && <details className="payroll-obligation-details"><summary>🔎 Xem chi tiết từng kỳ ({details.length})</summary><div className="responsive-data-table"><table><thead><tr><th>Tên nhân viên</th><th>Số tiền</th><th>Kỳ phát sinh từ</th><th>Kỳ phát sinh đến</th><th>Bắt đầu trừ từ</th><th>Nội dung</th><th>Trạng thái</th></tr></thead><tbody>{details.map((item, index) => <tr key={`${group.type}-${item.employee_name}-${item.period_start}-${index}`}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.period_start}</td><td>{item.period_end}</td><td>{item.due_from}</td><td>{item.content}</td><td>{item.status}</td></tr>)}</tbody></table></div></details>}
  </div>
}

export default function PayrollPageEnhanced({ user }) {
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
  const [periodNo, setPeriodNo] = useState(1)
  const [file, setFile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [draftSearch, setDraftSearch] = useState('')
  const [selected, setSelected] = useState([])
  const [config, setConfig] = useState(CONFIG_DEFAULT)
  const [accumulationRefunds, setAccumulationRefunds] = useState([])
  const [formerEmployees, setFormerEmployees] = useState([])
  const [refundForm, setRefundForm] = useState({ employee_name: '', amount: '', note: 'Hoàn trả tiền tích lũy khi nghỉ việc' })
  const [obligations, setObligations] = useState([])
  const [obligationGroups, setObligationGroups] = useState([])
  const [obligationForm, setObligationForm] = useState({ employee_name: '', amount: '', content: 'Chưa hoàn thành nghĩa vụ Vi phạm', due_from: '' })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const historyRequest = useRef(0)
  const draftImportRef = useRef(null)

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { await callback() } catch (error) { setNotice({ type: 'error', message: error.message }) } finally { setBusy('') }
  }

  const loadHistory = async (batchOverride = batch, employeeOverride = employee) => {
    const requestId = ++historyRequest.current
    const result = await veraApi.payrollHistory(batchOverride, employeeOverride)
    if (requestId === historyRequest.current) setHistory(result)
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
      setConfig(result.config || CONFIG_DEFAULT)
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
    let active = true
    if (!canCalculate || !month) return () => { active = false }
    setDraft(null)
    setDraftSearch('')
    setSelected([])
    veraApi.payrollDraft(month, periodNo)
      .then((result) => {
        if (!active) return
        const saved = result.draft || null
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
  }, [canCalculate, month, periodNo])

  const historyTotal = useMemo(() => history.records.reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [history.records])
  const draftTotal = useMemo(() => (draft?.rows || []).reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [draft])
  const draftSalaryTotal = useMemo(() => (draft?.rows || []).reduce((sum, item) => sum + Number(item['Tiền Lương'] || 0), 0), [draft])
  const draftRows = draft?.rows || []
  const draftNeedle = normalizeSearch(draftSearch)
  const visibleDraftRows = useMemo(() => {
    if (!draftNeedle) return draftRows
    return draftRows.filter((row) => normalizeSearch(`${row['Tên Hệ thống']} ${row['Họ và tên']}`).includes(draftNeedle))
  }, [draftRows, draftNeedle])
  const isBusy = Boolean(busy)
  const allVisibleSelected = visibleDraftRows.length > 0 && visibleDraftRows.every((row) => selected.includes(row['Tên Hệ thống']))

  const toggleAllSelected = () => {
    const names = visibleDraftRows.map((row) => row['Tên Hệ thống'])
    setSelected((current) => {
      if (allVisibleSelected) return current.filter((name) => !names.includes(name))
      return Array.from(new Set([...current, ...names]))
    })
  }

  const calculate = () => run('calculate', async () => {
    if (!file) throw new Error('Vui lòng chọn file Excel xuất từ TimeSoft.')
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new Error('Chỉ chấp nhận file Excel định dạng .xlsx.')
    if (file.size > 15 * 1024 * 1024) throw new Error('File Excel vượt quá giới hạn 15 MB.')
    const result = await veraApi.calculatePayroll(file, month, periodNo)
    setDraft(result)
    setDraftSearch('')
    setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
    setConfig(result.config || config)
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
      source_name: file?.name || draft.source_name || 'Bảng lương nháp',
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
      source_name: file?.name || draft.source_name || 'Bảng lương hoàn thành',
      rows: draft.rows,
    })
    try { await veraApi.deletePayrollDraft(month, periodNo) } catch { /* official payroll is already saved */ }
    setDraft(null)
    setSelected([])
    setFile(null)
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
        source_name: file?.name || draft.source_name || 'Bảng lương nháp',
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

  const importDraftExcel = (event) => {
    const selectedFile = event.target.files?.[0]
    event.target.value = ''
    if (!selectedFile) return
    void run('import-draft', async () => {
      if (!selectedFile.name.toLowerCase().endsWith('.xlsx')) throw new Error('Chỉ chấp nhận file Excel định dạng .xlsx.')
      if (selectedFile.size > 15 * 1024 * 1024) throw new Error('File Excel vượt quá giới hạn 15 MB.')
      const result = await veraApi.importPayrollDraft(selectedFile, month, periodNo)
      setDraft(result)
      setDraftSearch('')
      setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
      setNotice({ type: 'success', message: result.message })
    })
  }

  const emailDraft = () => run('email', async () => {
    const rows = (draft?.rows || []).filter((row) => selected.includes(row['Tên Hệ thống']))
    if (!rows.length) throw new Error('Chưa chọn nhân viên cần gửi email.')
    if (!window.confirm(`Gửi bảng lương qua email cho ${rows.length} nhân viên đã chọn?`)) return
    const result = await veraApi.emailPayroll({ start: draft.start, end: draft.end, rows })
    setNotice({ type: result.failed?.length ? 'warning' : 'success', message: result.message })
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

  const saveConfig = () => run('config', async () => {
    const result = await veraApi.savePayrollConfig(config)
    setConfig(result.config)
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
      setNotice({ type: 'success', message: `${result.message} Hãy Upload & tính lương lại để áp dụng vào bảng nháp.` })
    })
  }

  const removeAccumulationRefund = (id) => run(`accumulation-refund-${id}`, async () => {
    if (!window.confirm('Xóa cài đặt hoàn trả tiền tích lũy này?')) return
    const result = await veraApi.deletePayrollAccumulationRefund(id)
    setAccumulationRefunds((current) => current.filter((item) => item.id !== id))
    setNotice({ type: 'success', message: `${result.message} Hãy Upload & tính lương lại nếu bảng nháp đã được tạo.` })
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

  return <div className="feature-page payroll-page payroll-page-enhanced">
    <div className="page-heading"><div><span className="eyebrow"><WalletCards size={14} /> Kỳ 1 · Kỳ 2</span><h1>BẢNG LƯƠNG</h1><p>Tải file TimeSoft, tính lương, quản lý khấu trừ, hoàn thành và lưu lịch sử bảng lương.</p></div><button className="secondary-button" onClick={reload} disabled={isBusy}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button></div>
    {notice && <div className={notice.type === 'error' ? 'error-box' : notice.type === 'warning' ? 'warning-box' : 'success-box'}>{notice.message}</div>}

    {canCalculate && <section className="panel payroll-calculate-panel">
      <div className="panel-title-row"><div><h2>TÍNH BẢNG LƯƠNG</h2><p>Kỳ 1 là 01–15; Kỳ 2 là 16–cuối tháng. Nợ vi phạm đủ ngày bắt đầu trừ sẽ tự cộng vào “Nợ vi phạm kỳ trước”.</p></div></div>
      <div className="data-toolbar">
        <label>Tháng lương<input type="month" value={month} disabled={isBusy} onChange={(event) => setMonth(event.target.value)} /></label>
        <label>Kỳ lương<select value={periodNo} disabled={isBusy} onChange={(event) => setPeriodNo(Number(event.target.value))}><option value={1}>Kỳ 1</option><option value={2}>Kỳ 2</option></select></label>
        <label className="payroll-file">File TimeSoft<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={isBusy} onChange={(event) => setFile(event.target.files?.[0] || null)} /><small>{file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : 'Định dạng .xlsx · tối đa 15 MB'}</small></label>
        <button className="primary-button" onClick={calculate} disabled={isBusy}><Upload size={16} /> {busy === 'calculate' ? 'Đang tính…' : 'Upload & tính lương'}</button>
      </div>
      <input ref={draftImportRef} className="payroll-draft-file-input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={importDraftExcel} />
      <div className="payroll-draft-toolbar">
        <div><strong>BẢNG LƯƠNG NHÁP</strong><small>{draft?.rows?.length ? `${draft.period_label} · ${draft.rows.length} nhân viên${draft.saved_at ? ` · Đã lưu bởi ${draft.saved_by}` : ' · Chưa lưu trên máy chủ'}` : 'Chưa có dữ liệu nháp cho kỳ đang chọn.'}</small></div>
        <div className="list-actions">
          <button className="secondary-button" type="button" onClick={() => draftImportRef.current?.click()} disabled={isBusy}><Upload size={16} /> {busy === 'import-draft' ? 'Đang Import…' : 'Import Excel'}</button>
          {canExport && <button className="secondary-button" type="button" onClick={exportDraft} disabled={isBusy || !draftRows.length}><Download size={16} /> {busy === 'export-draft' ? 'Đang Export…' : 'Export to Excel'}</button>}
          {canSave && <button className="secondary-button" type="button" onClick={saveDraftSnapshot} disabled={isBusy || !draftRows.length}><Save size={16} /> {busy === 'save-draft' ? 'Đang lưu…' : 'Lưu bảng lương nháp'}</button>}
          {canSave && <button className="danger-button" type="button" onClick={deleteDraftSnapshot} disabled={isBusy || !draftRows.length}><Trash2 size={16} /> {busy === 'delete-draft' ? 'Đang xóa…' : 'Xóa bảng lương nháp'}</button>}
        </div>
      </div>
    </section>}

    {draft?.rows?.length > 0 && <section className="panel payroll-draft-panel">
      <div className="panel-title-row"><div><h2>{draft.period_label}</h2><p>{draft.rows.length} nhân viên · Tổng Tiền Lương {money(draftSalaryTotal)} · Tổng thực nhận {money(draftTotal)}</p></div><div className="list-actions">{canSave && <button className="primary-button" onClick={completePayroll} disabled={isBusy || draftSalaryTotal <= 0}><CheckCircle2 size={16} /> {busy === 'complete' ? 'Đang hoàn thành…' : 'Hoàn thành bảng lương'}</button>}{canEmail && <button className="secondary-button" onClick={emailDraft} disabled={isBusy}><Mail size={16} /> Gửi email ({selected.length})</button>}</div></div>
      <div className="payroll-search-toolbar">
        <label className="payroll-search-box">Tìm tên nhân viên<Search size={16} /><input type="search" value={draftSearch} disabled={isBusy} placeholder={`Tìm trong ${draft.period_label}`} onChange={(event) => setDraftSearch(event.target.value)} /></label>
        <div><strong>Hiển thị {visibleDraftRows.length}/{draftRows.length} nhân viên</strong></div>
      </div>
      {canEmail && <label className="payroll-select-all"><input type="checkbox" checked={allVisibleSelected} onChange={toggleAllSelected} disabled={isBusy || !visibleDraftRows.length} /> Chọn tất cả nhân viên đang hiển thị để gửi email</label>}
      <div className="responsive-data-table payroll-editor payroll-desktop-table payroll-fit-table"><table><thead><tr>{canEmail && <th>Gửi</th>}<th>Nhân viên</th><th>Lương</th>{Object.entries(EDIT_LABELS).map(([field, label]) => <th key={field}>{label}</th>)}<th>Thực nhận</th></tr></thead><tbody>{visibleDraftRows.map((row) => <tr className={isNonPositive(row) ? 'payroll-nonpositive' : ''} key={row['Tên Hệ thống']}>{canEmail && <td className="center"><input type="checkbox" aria-label={`Chọn gửi email cho ${row['Tên Hệ thống']}`} checked={selected.includes(row['Tên Hệ thống'])} disabled={isBusy} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} /></td>}<td><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']}</small><small>{row.Email || 'Chưa có email'}</small></td><td className="money-cell">{money(row['Tiền Lương'])}</td>{Object.keys(EDIT_LABELS).map((field) => <td key={field}><div className="payroll-cell-actions"><input className="payroll-money-input" type="number" min="0" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(row[field])} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} />{field === 'Tiền phạt trong tháng' && canManageObligations && Number(row[field] || 0) > 0 && <button type="button" className="secondary-button compact payroll-defer-button" disabled={isBusy} onClick={() => deferPenalty(row)}><ArrowRightCircle size={13} /> Chuyển kỳ sau</button>}</div></td>)}<td className="money-cell"><strong>{money(row['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
      <div className="payroll-mobile-list">{visibleDraftRows.map((row) => <article className={`payroll-mobile-card${isNonPositive(row) ? ' payroll-nonpositive' : ''}`} key={row['Tên Hệ thống']}>
        <header className="payroll-mobile-head"><div className="payroll-mobile-person">{canEmail && <input type="checkbox" checked={selected.includes(row['Tên Hệ thống'])} disabled={isBusy} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} />}<div><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']} · {row.Email || 'Chưa có email'}</small></div></div><span><small>Thực nhận</small><strong>{money(row['Số tiền thực nhận'])}</strong></span></header>
        <div className="payroll-mobile-summary"><span>Lương<strong>{money(row['Tiền Lương'])}</strong></span><span>Tổng khấu trừ<strong>{money(Number(row['Tích lũy'] || 0) + Number(row['Chi Phí Sinh Hoạt'] || 0) + Number(row['Tiền phạt trong tháng'] || 0) + Number(row['Vi phạm kỳ trước'] || 0) + Number(row['Tiền ứng lương'] || 0) + Number(row['Tiền hỗ trợ Locker'] || 0))}</strong></span></div>
        {canManageObligations && Number(row['Tiền phạt trong tháng'] || 0) > 0 && <button type="button" className="secondary-button" disabled={isBusy} onClick={() => deferPenalty(row)}><ArrowRightCircle size={15} /> Chuyển Vi phạm kỳ này sang kỳ sau</button>}
        <details className="payroll-mobile-details"><summary>Điều chỉnh các khoản lương</summary><div className="payroll-mobile-edit-grid">{Object.entries(EDIT_LABELS).map(([field, label]) => <label key={field}>{label}<input type="number" min="0" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(row[field])} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} /></label>)}</div></details>
      </article>)}</div>
      {!visibleDraftRows.length && <div className="setup-note">Không tìm thấy nhân viên phù hợp.</div>}
    </section>}

    {canManageObligations && <section className="panel">
      <div className="panel-title-row"><div><h2>NGHĨA VỤ VI PHẠM</h2><p>Khoản còn mở sẽ tự đưa vào “Nợ vi phạm kỳ trước” khi đến ngày bắt đầu trừ. Vi phạm được Admin chuyển kỳ sẽ xuất hiện ở đây.</p></div></div>
      <div className="payroll-obligation-groups">{obligationGroups.map((group) => <ObligationGroup key={group.type} group={group} />)}</div>
      <form className="payroll-obligation-form" onSubmit={addObligation}><label>Nhân viên<input required list="payroll-employee-options" disabled={isBusy} value={obligationForm.employee_name} onChange={(event) => setObligationForm({ ...obligationForm, employee_name: event.target.value })} /></label><label>Số tiền<input required type="number" min="1" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(obligationForm.amount)} onChange={(event) => setObligationForm({ ...obligationForm, amount: event.target.value })} /></label><label>Bắt đầu trừ từ<input required type="date" disabled={isBusy} value={obligationForm.due_from} onChange={(event) => setObligationForm({ ...obligationForm, due_from: event.target.value })} /></label><label>Nội dung<input required disabled={isBusy} value={obligationForm.content} onChange={(event) => setObligationForm({ ...obligationForm, content: event.target.value })} /></label><button className="primary-button" disabled={isBusy}><Plus size={16} /> Thêm nghĩa vụ</button></form>
      <datalist id="payroll-employee-options">{Array.from(new Set([...(history.employees || []), ...draftRows.map((row) => row['Tên Hệ thống'])])).map((name) => <option key={name}>{name}</option>)}</datalist>
      <div className="responsive-data-table"><table><thead><tr><th>Nhân viên</th><th>Số tiền</th><th>Bắt đầu trừ</th><th>Nội dung</th><th></th></tr></thead><tbody>{obligations.map((item) => <tr key={item.id}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.due_from}</td><td>{item.content}</td><td><button className="danger-button compact" disabled={isBusy} onClick={() => removeObligation(item.id)}><Trash2 size={14} /> Xóa</button></td></tr>)}</tbody></table></div>
      {!obligations.length && <div className="setup-note">Chưa có Nghĩa vụ vi phạm nhập/chuyển từ Web V2.</div>}
    </section>}

    <section className="panel">
      <div className="panel-title-row"><div><h2>LỊCH SỬ BẢNG LƯƠNG</h2><p>Danh sách các bảng lương đã hoàn thành và bộ lọc chi tiết từng nhân viên.</p></div>{canSyncLegacy && <button className="secondary-button" onClick={syncLegacy} disabled={isBusy}><RefreshCw size={16} className={busy === 'sync-legacy' ? 'spin' : ''} /> {busy === 'sync-legacy' ? 'Đang tải…' : 'Tải dữ liệu hệ thống cũ'}</button>}</div>

      <div className="saved-payroll-list">{savedBatches.map((item) => <article className="saved-payroll-card" key={item.batch}><header><div><h3>{item.batch}</h3><small>{item.saved_date ? `Lưu ${item.saved_date}${item.saved_time ? ` · ${item.saved_time}` : ''}` : 'Bảng lương đã lưu'}</small></div>{canDeleteHistory && <button className="danger-button compact" type="button" disabled={isBusy} onClick={() => deleteHistoryBatch(item.batch)}><Trash2 size={14} /> Xóa</button>}</header><div className="saved-payroll-metrics"><span>Nhân viên<strong>{item.employee_count}</strong></span><span>Tổng thực nhận<strong>{money(item.total_net)}</strong></span></div><button className="secondary-button" type="button" disabled={isBusy} onClick={() => setBatch(item.batch)}>Xem chi tiết</button></article>)}</div>
      {!savedBatches.length && <div className="setup-note">Chưa có bảng lương đã hoàn thành.</div>}

      <div className="data-toolbar history-delete-actions"><label>Kỳ lương<select value={batch} disabled={isBusy} onChange={(event) => setBatch(event.target.value)}><option value="">Tất cả kỳ lương</option>{history.batches.map((item) => <option key={item}>{item}</option>)}</select></label><label>Nhân viên<select value={employee} disabled={isBusy} onChange={(event) => setEmployee(event.target.value)}><option value="">Tất cả nhân viên</option>{history.employees.map((item) => <option key={item}>{item}</option>)}</select></label>{canExport && <button className="secondary-button" onClick={exportHistory} disabled={isBusy}><Download size={16} /> {busy === 'export-history' ? 'Đang xuất…' : 'Excel lịch sử'}</button>}{canDeleteHistory && <button className="danger-button" type="button" disabled={isBusy || !batch} onClick={() => deleteHistoryBatch(batch)}><Trash2 size={16} /> Xóa lịch sử kỳ đang chọn</button>}</div>
      <div className="metric-grid small payroll-history-metrics"><div className="metric-card"><span>Số dòng lương</span><strong>{history.records.length}</strong></div><div className="metric-card"><span>Tổng thực nhận đang xem</span><strong>{money(historyTotal)}</strong></div></div>
      <div className="responsive-data-table payroll-history-desktop"><table><thead><tr><th>Nhân viên</th><th>Kỳ lương</th><th>Lương</th><th>Hoàn trả tích lũy</th><th>Vi phạm</th><th>Nợ vi phạm kỳ trước</th><th>Thực nhận</th></tr></thead><tbody>{history.records.map((item, index) => <tr className={isNonPositive(item) ? 'payroll-nonpositive' : ''} key={`${item['Mã bản lưu']}-${item['Tên Hệ thống']}-${index}`}><td><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small></td><td>{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</td><td>{money(item['Tiền Lương'])}</td><td>{money(item['Hoàn trả tiền tích lũy'])}</td><td>{money(item['Tiền phạt trong tháng'])}</td><td>{money(item['Vi phạm kỳ trước'])}</td><td><strong>{money(item['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
      <div className="payroll-mobile-list payroll-history-mobile">{history.records.map((item, index) => <article className={`payroll-mobile-card${isNonPositive(item) ? ' payroll-nonpositive' : ''}`} key={`${item['Mã bản lưu']}-${item['Tên Hệ thống']}-${index}`}><header className="payroll-mobile-head"><div><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small></div><span><small>Thực nhận</small><strong>{money(item['Số tiền thực nhận'])}</strong></span></header><strong className="payroll-mobile-period">{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</strong><div className="payroll-mobile-summary payroll-history-summary"><span>Lương<strong>{money(item['Tiền Lương'])}</strong></span><span>Hoàn trả tích lũy<strong>{money(item['Hoàn trả tiền tích lũy'])}</strong></span><span>Vi phạm<strong>{money(item['Tiền phạt trong tháng'])}</strong></span><span>Nợ cũ<strong>{money(item['Vi phạm kỳ trước'])}</strong></span></div></article>)}</div>
      {!history.records.length && <div className="setup-note">Không có bảng lương phù hợp.</div>}
    </section>

    {canEditConfig && <section className="panel payroll-default-config-panel">
      <div className="panel-title-row"><div><h2><Settings2 size={17} /> CÀI ĐẶT KHẤU TRỪ MẶC ĐỊNH</h2><p>Đã chuyển xuống dưới LỊCH SỬ BẢNG LƯƠNG. Các mức này áp dụng khi tính bảng lương mới.</p></div><button className="primary-button" onClick={saveConfig} disabled={isBusy}><Save size={16} /> Lưu cài đặt</button></div>
      <div className="payroll-config-grid">
        <label>Chi phí sinh hoạt<input type="number" min="0" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(config.default_living_expense)} onChange={(event) => setConfig({ ...config, default_living_expense: Number(event.target.value) })} /></label>
        <label>Hỗ trợ Locker<input type="number" min="0" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(config.default_locker_support)} onChange={(event) => setConfig({ ...config, default_locker_support: Number(event.target.value) })} /></label>
        <label>Tiền trách nhiệm Leader (Kỳ 2)<input type="number" min="0" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(config.leader_responsibility_allowance)} onChange={(event) => setConfig({ ...config, leader_responsibility_allowance: Number(event.target.value) })} /></label>
      </div>
    </section>}

    {isAdmin && canEditConfig && <section className="panel payroll-accumulation-refund-panel">
      <div className="panel-title-row"><div><h2>HOÀN TRẢ TIỀN TÍCH LŨY – NHÂN VIÊN NGHỈ VIỆC</h2><p>Admin nhập thủ công; khoản hoàn trả được cộng đúng vào kỳ đang chọn và không khấu trừ Tích lũy thêm trong kỳ đó.</p></div></div>
      <form className="payroll-refund-form" onSubmit={addAccumulationRefund}>
        <label>Nhân viên nghỉ việc<select required disabled={isBusy} value={refundForm.employee_name} onChange={(event) => setRefundForm({ ...refundForm, employee_name: event.target.value })}><option value="">-- Chọn nhân viên --</option>{formerEmployees.map((item) => <option key={item.employee_name} value={item.employee_name}>{item.employee_name} · {item.employment_status}</option>)}</select></label>
        <label>Số tiền hoàn trả<input required type="number" min="1" inputMode="numeric" disabled={isBusy} value={numberInputDisplayValue(refundForm.amount)} onChange={(event) => setRefundForm({ ...refundForm, amount: event.target.value })} /></label>
        <label>Kỳ áp dụng<input readOnly value={`Kỳ ${periodNo} - Tháng ${Number(month.slice(5))}/${month.slice(0, 4)}`} /></label>
        <label>Ghi chú<input required disabled={isBusy} value={refundForm.note} onChange={(event) => setRefundForm({ ...refundForm, note: event.target.value })} /></label>
        <button className="primary-button" disabled={isBusy || !formerEmployees.length}><Plus size={16} /> Lưu hoàn trả</button>
      </form>
      <div className="responsive-data-table payroll-setting-table"><table><thead><tr><th>Nhân viên</th><th>Số tiền</th><th>Kỳ áp dụng</th><th>Ghi chú</th><th></th></tr></thead><tbody>{accumulationRefunds.map((item) => <tr key={item.id}><td><strong>{item.employee_name}</strong></td><td>{money(item.amount)}</td><td>{item.period_label || `${item.start} – ${item.end}`}</td><td>{item.note}</td><td><button type="button" className="danger-button compact" disabled={isBusy} onClick={() => removeAccumulationRefund(item.id)}><Trash2 size={14} /> Xóa</button></td></tr>)}</tbody></table></div>
      {!formerEmployees.length && <div className="setup-note">Chưa có nhân viên ở trạng thái Tạm thời nghỉ việc hoặc Đã nghỉ việc.</div>}
      {!accumulationRefunds.length && <div className="setup-note">Chưa có khoản hoàn trả tích lũy được cài đặt.</div>}
    </section>}
  </div>
}
