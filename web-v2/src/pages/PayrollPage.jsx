import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { Download, Mail, Plus, RefreshCw, Save, Settings2, Trash2, Upload, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useRef, useState } from 'react'
import { veraApi } from '../lib/api'
import VeraDateInput from '../components/VeraDateInput'
import VeraMoneyInput from '../components/VeraMoneyInput'

const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const currentMonth = () => {
  const date = new Date()
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`
}
const CONFIG_DEFAULT = { default_living_expense: 150000, default_locker_support: 80000, leader_responsibility_allowance: 0 }
const EDIT_LABELS = {
  'Tiền Hỗ Trợ Hoàn Lại': 'Trách nhiệm / hỗ trợ',
  'Hoàn trả tiền tích lũy': 'Hoàn trả tích lũy',
  'Tích lũy': 'Tích lũy',
  'Chi Phí Sinh Hoạt': 'Phí sinh hoạt',
  'Tiền phạt trong tháng': 'Vi phạm kỳ này',
  'Vi phạm kỳ trước': 'Nghĩa vụ vi phạm',
  'Tiền ứng lương': 'Tiền ứng',
  'Tiền hỗ trợ Locker': 'Hỗ trợ Locker',
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

function ObligationGroup({ group }) {
  const isNegative = group.type === 'Âm thực nhận'
  const summary = group.summary || []
  const details = group.details || []
  return <div className="payroll-obligation-group">
    <h3>{isNegative ? '🔴 Nợ do Thực nhận âm' : '⏭️ Nghĩa vụ Vi phạm Admin chủ động tạm hoãn'}</h3>
    <div className="responsive-data-table"><table data-ui-key="u-58f9a0b9f006"><thead><tr><th data-ui-key="u-e89ec8cd920b" data-ui-label-default="Tên nhân viên"><UiCustomText uiKey="u-e89ec8cd920b">Tên nhân viên</UiCustomText></th><th data-ui-key="u-33dd50082561">{isNegative ? 'Tổng còn nợ' : 'Tổng tạm hoãn'}</th><th data-ui-key="u-47bc2a72a91f">{isNegative ? 'Số kỳ còn nợ' : 'Số kỳ tạm hoãn'}</th><th data-ui-key="u-89ab5834950b">{isNegative ? 'Kỳ nợ gần nhất' : 'Kỳ tạm hoãn gần nhất'}</th><th data-ui-key="u-1003407fb2da" data-ui-label-default="Bắt đầu trừ từ"><UiCustomText uiKey="u-1003407fb2da">Bắt đầu trừ từ</UiCustomText></th></tr></thead><tbody>{summary.map((item) => <tr key={`${group.type}-${item.employee_name}`}><td>{item.employee_name}</td><td>{money(item.total)}</td><td className="center">{item.period_count}</td><td>{item.latest_period}</td><td>{item.due_from}</td></tr>)}</tbody></table></div>
    {!summary.length && <div className="setup-note">Không có khoản đang mở.</div>}
    {details.length > 0 && <details className="payroll-obligation-details"><summary>🔎 Xem chi tiết từng kỳ ({details.length})</summary><div className="responsive-data-table"><table data-ui-key="u-a34bd4b3c630"><thead><tr><th data-ui-key="u-f803d0750f8e" data-ui-label-default="Tên nhân viên"><UiCustomText uiKey="u-f803d0750f8e">Tên nhân viên</UiCustomText></th><th data-ui-key="u-6069089546c7" data-ui-label-default="Số tiền"><UiCustomText uiKey="u-6069089546c7">Số tiền</UiCustomText></th><th data-ui-key="u-2518ded806b6" data-ui-label-default="Kỳ phát sinh từ"><UiCustomText uiKey="u-2518ded806b6">Kỳ phát sinh từ</UiCustomText></th><th data-ui-key="u-956e084fcdd9" data-ui-label-default="Kỳ phát sinh đến"><UiCustomText uiKey="u-956e084fcdd9">Kỳ phát sinh đến</UiCustomText></th><th data-ui-key="u-1c3e52870fc8" data-ui-label-default="Bắt đầu trừ từ"><UiCustomText uiKey="u-1c3e52870fc8">Bắt đầu trừ từ</UiCustomText></th><th data-ui-key="u-7023d2c2fc44" data-ui-label-default="Nội dung"><UiCustomText uiKey="u-7023d2c2fc44">Nội dung</UiCustomText></th><th data-ui-key="u-ddb59a283e7e" data-ui-label-default="Trạng thái"><UiCustomText uiKey="u-ddb59a283e7e">Trạng thái</UiCustomText></th></tr></thead><tbody>{details.map((item, index) => <tr key={`${group.type}-${item.employee_name}-${item.period_start}-${index}`}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.period_start}</td><td>{item.period_end}</td><td>{item.due_from}</td><td>{item.content}</td><td>{item.status}</td></tr>)}</tbody></table></div></details>}
  </div>
}

export default function PayrollPage({ user }) {
  usePageRefresh(() => reload(), () => Boolean(busy || JSON.stringify(config) !== configBaseline))
  const permissions = user?.permissions || {}
  const isAdmin = String(user?.role || '').toLowerCase() === 'admin'
  const canCalculate = isAdmin || permissions.payroll_calculate
  const canEditConfig = isAdmin || permissions.payroll_config_edit
  const canManageObligations = isAdmin || permissions.payroll_penalty_obligation
  const canSyncLegacy = isAdmin || permissions.payroll_history_edit
  const canSave = isAdmin || permissions.payroll_save
  const canEmail = isAdmin || permissions.payroll_email
  const canExport = isAdmin || permissions.payroll_export
  const [batch, setBatch] = useState('')
  const [employee, setEmployee] = useState('')
  const [history, setHistory] = useState({ records: [], batches: [], employees: [] })
  const [month, setMonth] = useState(currentMonth())
  const [periodNo, setPeriodNo] = useState(1)
  const [file, setFile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [selected, setSelected] = useState([])
  const [config, setConfig] = useState(CONFIG_DEFAULT)
  const [configBaseline, setConfigBaseline] = useState(() => JSON.stringify(CONFIG_DEFAULT))
  const [obligations, setObligations] = useState([])
  const [obligationGroups, setObligationGroups] = useState([])
  const [obligationForm, setObligationForm] = useState({ employee_name: '', amount: '', content: 'Chưa hoàn thành nghĩa vụ Vi phạm', due_from: '' })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)
  const [emailProgress, setEmailProgress] = useState(null)
  const historyRequest = useRef(0)
  const draftImportRef = useRef(null)

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { await callback() } catch (error) { setNotice({ type: 'error', message: error.message }) } finally { setBusy('') }
  }
  const loadHistory = async () => {
    const requestId = ++historyRequest.current
    const result = await veraApi.payrollHistory(batch, employee)
    if (requestId === historyRequest.current) setHistory(result)
    return result
  }
  const loadSupporting = async () => {
    if (canCalculate || canEditConfig) {
      const result = await veraApi.payrollConfig()
      setConfig(result.config || CONFIG_DEFAULT); setConfigBaseline(JSON.stringify(result.config || CONFIG_DEFAULT))
    }
    if (canManageObligations) {
      const result = await veraApi.payrollObligations()
      setObligations(result.obligations || [])
      setObligationGroups(result.groups || [])
    }
  }
  const reload = () => run('load', async () => { await loadHistory(); await loadSupporting() })
  useEffect(() => { void reload() }, [batch, employee]) // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => {
    let active = true
    if (!canCalculate || !month) return () => { active = false }
    setDraft(null)
    setSelected([])
    veraApi.payrollDraft(month, periodNo)
      .then((result) => {
        if (!active) return
        const saved = result.draft || null
        setDraft(saved)
        setSelected((saved?.rows || []).map((row) => row['Tên Hệ thống']))
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
  const isBusy = Boolean(busy)
  const allSelected = draftRows.length > 0 && draftRows.every((row) => selected.includes(row['Tên Hệ thống']))

  const toggleAllSelected = () => {
    setSelected(allSelected ? [] : draftRows.map((row) => row['Tên Hệ thống']))
  }

  const calculate = () => run('calculate', async () => {
    if (!file) throw new Error('Vui lòng chọn file Excel xuất từ TimeSoft.')
    if (!file.name.toLowerCase().endsWith('.xlsx')) throw new Error('Chỉ chấp nhận file Excel định dạng .xlsx.')
    if (file.size > 15 * 1024 * 1024) throw new Error('File Excel vượt quá giới hạn 15 MB.')
    const result = await veraApi.calculatePayroll(file, month, periodNo)
    setDraft(result)
    setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
    setConfig(result.config || config); setConfigBaseline(JSON.stringify(result.config || config))
    const summary = result.source_summary || {}
    const detail = summary.matched_tip_rows
      ? `${summary.matched_tip_rows} dòng Tip · Tổng Tiền Lương ${money(summary.matched_salary_total)}`
      : ''
    setNotice({
      type: result.unmatched?.length ? 'warning' : 'success',
      message: result.unmatched?.length
        ? `Đã tính ${result.period_label} · ${detail}. Chưa khớp tài khoản: ${result.unmatched.join(', ')}`
        : `Đã tính ${result.period_label}${detail ? ` · ${detail}` : ''}.`,
    })
  })

  const editMoney = (username, field, value) => {
    setDraft((current) => ({
      ...current,
      saved_at: '',
      saved_by: '',
      rows: current.rows.map((row) => row['Tên Hệ thống'] === username
        ? recalculate({ ...row, [field]: Number(value || 0) }) : row),
    }))
  }

  const savePayrollPeriod = () => run('save', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương để lưu.')
    if (draftSalaryTotal <= 0) throw new Error('Tổng Tiền Lương đang bằng 0. Không thể lưu chính thức; hãy kiểm tra file TimeSoft và số dòng Tip.')
    if (!window.confirm(`Lưu ${draft.period_label}? Bản lưu cũ của đúng kỳ này (nếu có) sẽ được thay thế.`)) return
    const result = await veraApi.savePayroll({ start: draft.start, end: draft.end, source_name: file?.name || draft.source_name || 'Excel upload', rows: draft.rows })
    await loadHistory()
    setNotice({ type: 'success', message: result.message })
  })

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

  const importDraftExcel = (event) => {
    const selectedFile = event.target.files?.[0]
    event.target.value = ''
    if (!selectedFile) return
    void run('import-draft', async () => {
      if (!selectedFile.name.toLowerCase().endsWith('.xlsx')) throw new Error('Chỉ chấp nhận file Excel định dạng .xlsx.')
      if (selectedFile.size > 15 * 1024 * 1024) throw new Error('File Excel vượt quá giới hạn 15 MB.')
      const result = await veraApi.importPayrollDraft(selectedFile, month, periodNo)
      setDraft(result)
      setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
      setNotice({ type: 'success', message: result.message })
    })
  }

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
      setNotice({
        type: failed.length ? 'warning' : 'success',
        message: `Đã gửi ${sent.length}/${rows.length} email; lỗi ${failed.length}.`,
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
    setNotice({ type: 'success', message: 'Đã xuất Excel bản lương cũ theo bộ lọc đang xem.' })
  })

  const saveConfig = () => run('config', async () => {
    const result = await veraApi.savePayrollConfig(config)
    setConfig(result.config); setConfigBaseline(JSON.stringify(result.config))
    setNotice({ type: 'success', message: result.message })
  })

  const addObligation = (event) => {
    event.preventDefault()
    run('obligation', async () => {
      const result = await veraApi.createPayrollObligation({ ...obligationForm, amount: Number(obligationForm.amount) })
      setObligations((current) => [...current, result.obligation])
      setObligationForm({ employee_name: '', amount: '', content: 'Chưa hoàn thành nghĩa vụ Vi phạm', due_from: '' })
      setNotice({ type: 'success', message: result.message })
    })
  }
  const removeObligation = (id) => run(`obligation-${id}`, async () => {
    if (!window.confirm('Xóa Nghĩa vụ vi phạm này?')) return
    const result = await veraApi.deletePayrollObligation(id)
    setObligations((current) => current.filter((item) => item.id !== id))
    setNotice({ type: 'success', message: result.message })
  })
  const syncLegacy = () => run('sync-legacy', async () => {
    if (!window.confirm('Tải lại lịch sử bảng lương và Nghĩa vụ vi phạm từ hệ thống cũ? Dữ liệu Web V2 đã lưu vẫn được ưu tiên hiển thị.')) return
    const result = await veraApi.syncLegacyPayroll()
    await loadHistory()
    await loadSupporting()
    setNotice({ type: 'success', message: result.message })
  })

  return <div className="feature-page payroll-page">
    <div data-ui-key="u-fa114796e72b" className="page-heading"><div><span className="eyebrow"><WalletCards size={14} /> Kỳ 1 · Kỳ 2</span><h1>BẢNG LƯƠNG</h1><p>Tải file TimeSoft, tính lương, quản lý khấu trừ và gửi phiếu lương qua email.</p></div><button data-ui-key="u-4a2bbe33310c" data-ui-label-default="Làm mới" className="secondary-button" onClick={reload} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /><UiCustomText uiKey="u-4a2bbe33310c"> Làm mới</UiCustomText></button></div>
    <StableFeedback>{notice && <div className={notice.type === 'error' ? 'error-box' : notice.type === 'warning' ? 'warning-box' : 'success-box'}>{notice.message}</div>}</StableFeedback>

    {canCalculate && <section data-ui-key="u-ea9b3a18e95a" className="panel payroll-calculate-panel">
      <div data-ui-key="u-0691637823dd" className="panel-title-row"><div><h2>TÍNH BẢNG LƯƠNG</h2><p>Kỳ 1 là 01–15; Kỳ 2 là 16–cuối tháng. Tiền trách nhiệm Leader chỉ tự cộng ở Kỳ 2.</p></div></div>
      <UiToolbar data-ui-key="u-185184c5b061" className="data-toolbar">
        <label>Tháng lương<input type="month" value={month} disabled={isBusy} onChange={(event) => setMonth(event.target.value)} /></label>
        <label>Kỳ lương<select value={periodNo} disabled={isBusy} onChange={(event) => setPeriodNo(Number(event.target.value))}><option value={1}>Kỳ 1</option><option value={2}>Kỳ 2</option></select></label>
        <label className="payroll-file">File TimeSoft<input type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" disabled={isBusy} onChange={(event) => setFile(event.target.files?.[0] || null)} /><small>{file ? `${file.name} · ${(file.size / 1024 / 1024).toFixed(1)} MB` : 'Định dạng .xlsx · tối đa 15 MB'}</small></label>
        <button data-ui-key="u-82075635fa0d" className="primary-button" onClick={calculate} disabled={isBusy}><Upload size={16} /> {busy === 'calculate' ? 'Đang tính…' : 'Upload & tính lương'}</button>
      </UiToolbar>
      <input ref={draftImportRef} className="payroll-draft-file-input" type="file" accept=".xlsx,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet" onChange={importDraftExcel} />
      <UiToolbar data-ui-key="u-2a2ef9ec7d78" className="payroll-draft-toolbar">
        <div><strong>BẢNG LƯƠNG NHÁP</strong><small>{draft?.rows?.length ? `${draft.period_label} · ${draft.rows.length} nhân viên${draft.saved_at ? ` · Đã lưu bởi ${draft.saved_by}` : ' · Chưa lưu trên máy chủ'}` : 'Chưa có dữ liệu nháp cho kỳ đang chọn.'}</small></div>
        <UiToolbar data-ui-key="u-ed85724d12da" className="list-actions">
          <button data-ui-key="u-8ddd25c62bd4" className="secondary-button" type="button" onClick={() => draftImportRef.current?.click()} disabled={isBusy}><Upload size={16} /> {busy === 'import-draft' ? 'Đang Import…' : 'Import Excel'}</button>
          {canExport && <button data-ui-key="u-5ec3207fdacd" className="secondary-button" type="button" onClick={exportDraft} disabled={isBusy || !draftRows.length}><Download size={16} /> {busy === 'export-draft' ? 'Đang Export…' : 'Export to Excel'}</button>}
          {canSave && <button data-ui-key="u-58282fa9bdca" className="primary-button" type="button" onClick={saveDraftSnapshot} disabled={isBusy || !draftRows.length}><Save size={16} /> {busy === 'save-draft' ? 'Đang lưu…' : 'Lưu bảng lương nháp'}</button>}
          {canSave && <button data-ui-key="u-4280c92e55e8" className="danger-button" type="button" onClick={deleteDraftSnapshot} disabled={isBusy || !draftRows.length}><Trash2 size={16} /> {busy === 'delete-draft' ? 'Đang xóa…' : 'Xóa bảng lương nháp'}</button>}
        </UiToolbar>
      </UiToolbar>
    </section>}

    {canEditConfig && <section data-ui-key="u-74dca510f115" className="panel">
      <div data-ui-key="u-1dfc43d16241" className="panel-title-row"><div><h2><Settings2 size={17} /> CÀI ĐẶT KHẤU TRỪ MẶC ĐỊNH</h2><p>Áp dụng khi tính bảng lương mới.</p></div><button data-ui-key="u-e4b04e097012" data-ui-label-default="Lưu cài đặt" className="primary-button" onClick={saveConfig} disabled={isBusy}><Save size={16} /><UiCustomText uiKey="u-e4b04e097012"> Lưu cài đặt</UiCustomText></button></div>
      <div className="payroll-config-grid">
        <label>Chi phí sinh hoạt<VeraMoneyInput disabled={isBusy} value={config.default_living_expense} onChange={(event) => setConfig({ ...config, default_living_expense: Number(event.target.value) })} /></label>
        <label>Hỗ trợ Locker<VeraMoneyInput disabled={isBusy} value={config.default_locker_support} onChange={(event) => setConfig({ ...config, default_locker_support: Number(event.target.value) })} /></label>
        <label>Tiền trách nhiệm Leader (Kỳ 2)<VeraMoneyInput disabled={isBusy} value={config.leader_responsibility_allowance} onChange={(event) => setConfig({ ...config, leader_responsibility_allowance: Number(event.target.value) })} /></label>
      </div>
    </section>}

    {draft?.rows?.length > 0 && <section data-ui-key="u-3e019728145b" className="panel payroll-draft-panel">
      <div data-ui-key="u-b525b10486e5" className="panel-title-row"><div><h2>{draft.period_label}</h2><p>{draft.rows.length} nhân viên · Tổng Tiền Lương {money(draftSalaryTotal)} · Tổng thực nhận {money(draftTotal)}</p></div><UiToolbar data-ui-key="u-75a9c6f829c2" className="list-actions">{canSave && <button data-ui-key="u-abc3ff7ade06" data-ui-label-default="Lưu bảng lương chính thức" className="primary-button" onClick={savePayrollPeriod} disabled={isBusy || draftSalaryTotal <= 0}><Save size={16} /><UiCustomText uiKey="u-abc3ff7ade06"> Lưu bảng lương chính thức</UiCustomText></button>}{canEmail && <button data-ui-key="u-4e1d80c266ef" className="secondary-button" onClick={emailDraft} disabled={isBusy}><Mail size={16} /> {busy === 'email' && emailProgress ? `Đang gửi ${emailProgress.processed}/${emailProgress.total}…` : `Gửi email (${selected.length})`}</button>}</UiToolbar></div>
      {canEmail && <label className="payroll-select-all"><input type="checkbox" checked={allSelected} onChange={toggleAllSelected} disabled={isBusy} /> Chọn tất cả {draftRows.length} nhân viên để gửi email</label>}
      <div className="responsive-data-table payroll-editor payroll-desktop-table"><table data-ui-key="u-5798948f1c8a"><thead><tr>{canEmail && <th data-ui-key="u-fbc878d0f2c3" data-ui-label-default="Gửi"><UiCustomText uiKey="u-fbc878d0f2c3">Gửi</UiCustomText></th>}<th data-ui-key="u-3af4f3b68548" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-3af4f3b68548">Nhân viên</UiCustomText></th><th data-ui-key="u-01ad48301fff" data-ui-label-default="Lương"><UiCustomText uiKey="u-01ad48301fff">Lương</UiCustomText></th>{Object.entries(EDIT_LABELS).map(([field, label]) => <th data-ui-key="u-33f4a3092e7c" key={field}>{label}</th>)}<th data-ui-key="u-f067b843a298" data-ui-label-default="Thực nhận"><UiCustomText uiKey="u-f067b843a298">Thực nhận</UiCustomText></th></tr></thead><tbody>{draftRows.map((row) => <tr key={row['Tên Hệ thống']}>{canEmail && <td className="center"><input type="checkbox" aria-label={`Chọn gửi email cho ${row['Tên Hệ thống']}`} checked={selected.includes(row['Tên Hệ thống'])} disabled={isBusy} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} /></td>}<td><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']}</small><small>{row.Email || 'Chưa có email'}</small></td><td className="money-cell">{money(row['Tiền Lương'])}</td>{Object.keys(EDIT_LABELS).map((field) => <td key={field}><VeraMoneyInput className="payroll-money-input" disabled={isBusy} value={row[field]} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} /></td>)}<td className="money-cell"><strong>{money(row['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
      <div className="payroll-mobile-list">{draftRows.map((row) => <article className="payroll-mobile-card" key={row['Tên Hệ thống']}>
        <header className="payroll-mobile-head">
          <div className="payroll-mobile-person">{canEmail && <input type="checkbox" aria-label={`Chọn gửi email cho ${row['Tên Hệ thống']}`} checked={selected.includes(row['Tên Hệ thống'])} disabled={isBusy} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} />}<div><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']} · {row.Email || 'Chưa có email'}</small></div></div>
          <span><small>Thực nhận</small><strong>{money(row['Số tiền thực nhận'])}</strong></span>
        </header>
        <div className="payroll-mobile-summary"><span>Lương<strong>{money(row['Tiền Lương'])}</strong></span><span>Tổng khấu trừ<strong>{money(Number(row['Tích lũy'] || 0) + Number(row['Chi Phí Sinh Hoạt'] || 0) + Number(row['Tiền phạt trong tháng'] || 0) + Number(row['Vi phạm kỳ trước'] || 0) + Number(row['Tiền ứng lương'] || 0) + Number(row['Tiền hỗ trợ Locker'] || 0))}</strong></span></div>
        <details className="payroll-mobile-details"><summary>Điều chỉnh các khoản lương</summary><div className="payroll-mobile-edit-grid">{Object.entries(EDIT_LABELS).map(([field, label]) => <label key={field}>{label}<VeraMoneyInput disabled={isBusy} value={row[field]} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} /></label>)}</div></details>
      </article>)}</div>
    </section>}

    {canManageObligations && <section data-ui-key="u-bb7d95609001" className="panel">
      <div data-ui-key="u-1040fe4914d6" className="panel-title-row"><div><h2>NGHĨA VỤ VI PHẠM</h2><p>Khoản còn mở sẽ đưa vào “Vi phạm kỳ trước” từ ngày bắt đầu trừ.</p></div></div>
      <div className="payroll-obligation-groups">{obligationGroups.map((group) => <ObligationGroup key={group.type} group={group} />)}</div>
      <form className="payroll-obligation-form" onSubmit={addObligation}><label>Nhân viên<input required list="payroll-employee-options" disabled={isBusy} value={obligationForm.employee_name} onChange={(event) => setObligationForm({ ...obligationForm, employee_name: event.target.value })} /></label><label>Số tiền<VeraMoneyInput required disabled={isBusy} value={obligationForm.amount} onChange={(event) => setObligationForm({ ...obligationForm, amount: event.target.value })} /></label><label>Bắt đầu trừ từ<VeraDateInput required aria-label="Bắt đầu trừ từ" disabled={isBusy} value={obligationForm.due_from} onChange={(event) => setObligationForm({ ...obligationForm, due_from: event.target.value })} /></label><label>Nội dung<input required disabled={isBusy} value={obligationForm.content} onChange={(event) => setObligationForm({ ...obligationForm, content: event.target.value })} /></label><button data-ui-key="u-4ca8aad57e00" data-ui-label-default="Thêm nghĩa vụ" className="primary-button" disabled={isBusy}><Plus size={16} /><UiCustomText uiKey="u-4ca8aad57e00"> Thêm nghĩa vụ</UiCustomText></button></form>
      <datalist id="payroll-employee-options">{Array.from(new Set([...(history.employees || []), ...(draft?.rows || []).map((row) => row['Tên Hệ thống'])])).map((name) => <option key={name}>{name}</option>)}</datalist>
      <div className="responsive-data-table"><table data-ui-key="u-926b83f6d6f8"><thead><tr><th data-ui-key="u-98a3b3a246c3" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-98a3b3a246c3">Nhân viên</UiCustomText></th><th data-ui-key="u-5a2a1b728e0a" data-ui-label-default="Số tiền"><UiCustomText uiKey="u-5a2a1b728e0a">Số tiền</UiCustomText></th><th data-ui-key="u-f9f4cde04975" data-ui-label-default="Bắt đầu trừ"><UiCustomText uiKey="u-f9f4cde04975">Bắt đầu trừ</UiCustomText></th><th data-ui-key="u-89a6199b803f" data-ui-label-default="Nội dung"><UiCustomText uiKey="u-89a6199b803f">Nội dung</UiCustomText></th><th data-ui-key="u-57a72e195ae5"></th></tr></thead><tbody>{obligations.map((item) => <tr key={item.id}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.due_from}</td><td>{item.content}</td><td><button data-ui-key="u-aed57d41df44" data-ui-label-default="Xóa" className="danger-button compact" disabled={isBusy} onClick={() => removeObligation(item.id)}><Trash2 size={14} /><UiCustomText uiKey="u-aed57d41df44"> Xóa</UiCustomText></button></td></tr>)}</tbody></table></div>
      {!obligations.length && <div className="setup-note">Chưa có Nghĩa vụ vi phạm nhập từ Web V2.</div>}
    </section>}

    <section data-ui-key="u-3781876d711c" className="panel">
      <div data-ui-key="u-346b4cd0cd31" className="panel-title-row"><div><h2>LỊCH SỬ BẢNG LƯƠNG</h2><p>Bộ lọc nhân viên dùng đối chiếu chính xác, không trộn dữ liệu người có tên gần giống.</p></div>{canSyncLegacy && <button data-ui-key="u-330843aef494" className="secondary-button" onClick={syncLegacy} disabled={isBusy}><RefreshCw size={16} className={busy === 'sync-legacy' ? 'spin' : ''} /> {busy === 'sync-legacy' ? 'Đang tải…' : 'Tải dữ liệu hệ thống cũ'}</button>}</div>
      <UiToolbar data-ui-key="u-3f3709b00526" className="data-toolbar"><label>Kỳ lương<select value={batch} disabled={isBusy} onChange={(event) => setBatch(event.target.value)}><option value="">Tất cả kỳ lương</option>{history.batches.map((item) => <option key={item}>{item}</option>)}</select></label><label>Nhân viên<select value={employee} disabled={isBusy} onChange={(event) => setEmployee(event.target.value)}><option value="">Tất cả nhân viên</option>{history.employees.map((item) => <option key={item}>{item}</option>)}</select></label>{canExport && <button data-ui-key="u-c31b31228608" className="secondary-button" onClick={exportHistory} disabled={isBusy}><Download size={16} /> {busy === 'export-history' ? 'Đang xuất…' : 'Excel lịch sử'}</button>}</UiToolbar>
      <div className="metric-grid small payroll-history-metrics"><div data-ui-key="u-3145cf31c893" className="metric-card"><span>Số dòng lương</span><strong>{history.records.length}</strong></div><div data-ui-key="u-cdac563907e3" className="metric-card"><span>Tổng thực nhận đang xem</span><strong>{money(historyTotal)}</strong></div></div>
      <div className="responsive-data-table payroll-history-desktop"><table data-ui-key="u-ebd0f8b7344c"><thead><tr><th data-ui-key="u-8686bcf07bea" data-ui-label-default="Nhân viên"><UiCustomText uiKey="u-8686bcf07bea">Nhân viên</UiCustomText></th><th data-ui-key="u-ec9d77bf92d0" data-ui-label-default="Kỳ lương"><UiCustomText uiKey="u-ec9d77bf92d0">Kỳ lương</UiCustomText></th><th data-ui-key="u-8df1b9ac740b" data-ui-label-default="Lương"><UiCustomText uiKey="u-8df1b9ac740b">Lương</UiCustomText></th><th data-ui-key="u-dc668ddc87d8" data-ui-label-default="Hoàn trả tích lũy"><UiCustomText uiKey="u-dc668ddc87d8">Hoàn trả tích lũy</UiCustomText></th><th data-ui-key="u-703029c1dba0" data-ui-label-default="Vi phạm"><UiCustomText uiKey="u-703029c1dba0">Vi phạm</UiCustomText></th><th data-ui-key="u-b041b074e729" data-ui-label-default="Nghĩa vụ cũ"><UiCustomText uiKey="u-b041b074e729">Nghĩa vụ cũ</UiCustomText></th><th data-ui-key="u-d71ad7c82f5b" data-ui-label-default="Thực nhận"><UiCustomText uiKey="u-d71ad7c82f5b">Thực nhận</UiCustomText></th></tr></thead><tbody>{history.records.map((item, index) => <tr key={`${item['Mã bản lưu']}-${item['Tên Hệ thống']}-${index}`}><td><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small></td><td>{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</td><td>{money(item['Tiền Lương'])}</td><td>{money(item['Hoàn trả tiền tích lũy'])}</td><td>{money(item['Tiền phạt trong tháng'])}</td><td>{money(item['Vi phạm kỳ trước'])}</td><td><strong>{money(item['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
      <div className="payroll-mobile-list payroll-history-mobile">{history.records.map((item, index) => <article className="payroll-mobile-card" key={`${item['Mã bản lưu']}-${item['Tên Hệ thống']}-${index}`}><header className="payroll-mobile-head"><div><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small></div><span><small>Thực nhận</small><strong>{money(item['Số tiền thực nhận'])}</strong></span></header><strong className="payroll-mobile-period">{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</strong><div className="payroll-mobile-summary payroll-history-summary"><span>Lương<strong>{money(item['Tiền Lương'])}</strong></span><span>Hoàn trả tích lũy<strong>{money(item['Hoàn trả tiền tích lũy'])}</strong></span><span>Vi phạm<strong>{money(item['Tiền phạt trong tháng'])}</strong></span><span>Nghĩa vụ cũ<strong>{money(item['Vi phạm kỳ trước'])}</strong></span></div></article>)}</div>
      {!history.records.length && <div className="setup-note">Không có bảng lương phù hợp.</div>}
    </section>
  </div>
}
