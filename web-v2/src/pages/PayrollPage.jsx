import { Download, Mail, Plus, RefreshCw, Save, Settings2, Trash2, Upload, WalletCards } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'

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

export default function PayrollPage({ user }) {
  const permissions = user?.permissions || {}
  const [batch, setBatch] = useState('')
  const [employee, setEmployee] = useState('')
  const [history, setHistory] = useState({ records: [], batches: [], employees: [] })
  const [month, setMonth] = useState(currentMonth())
  const [periodNo, setPeriodNo] = useState(1)
  const [file, setFile] = useState(null)
  const [draft, setDraft] = useState(null)
  const [selected, setSelected] = useState([])
  const [config, setConfig] = useState(CONFIG_DEFAULT)
  const [obligations, setObligations] = useState([])
  const [obligationForm, setObligationForm] = useState({ employee_name: '', amount: '', content: 'Chưa hoàn thành nghĩa vụ Vi phạm', due_from: '' })
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { await callback() } catch (error) { setNotice({ type: 'error', message: error.message }) } finally { setBusy('') }
  }
  const loadHistory = async () => setHistory(await veraApi.payrollHistory(batch, employee))
  const loadSupporting = async () => {
    const jobs = []
    if (permissions.payroll_calculate || permissions.payroll_config_edit) jobs.push(veraApi.payrollConfig().then((result) => setConfig(result.config || CONFIG_DEFAULT)))
    if (permissions.payroll_penalty_obligation) jobs.push(veraApi.payrollObligations().then((result) => setObligations(result.obligations || [])))
    await Promise.all(jobs)
  }
  const reload = () => run('load', async () => { await Promise.all([loadHistory(), loadSupporting()]) })
  useEffect(() => { void reload() }, [batch, employee]) // eslint-disable-line react-hooks/exhaustive-deps

  const historyTotal = useMemo(() => history.records.reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [history.records])
  const draftTotal = useMemo(() => (draft?.rows || []).reduce((sum, item) => sum + Number(item['Số tiền thực nhận'] || 0), 0), [draft])

  const calculate = () => run('calculate', async () => {
    if (!file) throw new Error('Vui lòng chọn file Excel xuất từ TimeSoft.')
    const result = await veraApi.calculatePayroll(file, month, periodNo)
    setDraft(result)
    setSelected((result.rows || []).map((row) => row['Tên Hệ thống']))
    setConfig(result.config || config)
    setNotice({ type: result.unmatched?.length ? 'warning' : 'success', message: result.unmatched?.length ? `Đã tính lương; chưa khớp tài khoản: ${result.unmatched.join(', ')}` : `Đã tính ${result.period_label}.` })
  })

  const editMoney = (username, field, value) => {
    setDraft((current) => ({
      ...current,
      rows: current.rows.map((row) => row['Tên Hệ thống'] === username
        ? recalculate({ ...row, [field]: Number(value || 0) }) : row),
    }))
  }

  const saveDraft = () => run('save', async () => {
    if (!draft?.rows?.length) throw new Error('Chưa có bảng lương để lưu.')
    if (!window.confirm(`Lưu ${draft.period_label}? Bản lưu cũ của đúng kỳ này (nếu có) sẽ được thay thế.`)) return
    const result = await veraApi.savePayroll({ start: draft.start, end: draft.end, source_name: file?.name || 'Excel upload', rows: draft.rows })
    await loadHistory()
    setNotice({ type: 'success', message: result.message })
  })

  const emailDraft = () => run('email', async () => {
    const rows = (draft?.rows || []).filter((row) => selected.includes(row['Tên Hệ thống']))
    if (!rows.length) throw new Error('Chưa chọn nhân viên cần gửi email.')
    if (!window.confirm(`Gửi bảng lương qua email cho ${rows.length} nhân viên đã chọn?`)) return
    const result = await veraApi.emailPayroll({ start: draft.start, end: draft.end, rows })
    setNotice({ type: result.failed?.length ? 'warning' : 'success', message: result.message })
  })

  const saveConfig = () => run('config', async () => {
    const result = await veraApi.savePayrollConfig(config)
    setConfig(result.config)
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

  return <div className="feature-page payroll-page">
    <div className="page-heading"><div><span className="eyebrow"><WalletCards size={14} /> Kỳ 1 · Kỳ 2</span><h1>BẢNG LƯƠNG</h1><p>Tải file TimeSoft, tính lương, quản lý khấu trừ và gửi phiếu lương qua email.</p></div><button className="secondary-button" onClick={reload} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button></div>
    {notice && <div className={notice.type === 'error' ? 'error-box' : notice.type === 'warning' ? 'warning-box' : 'success-box'}>{notice.message}</div>}

    {permissions.payroll_calculate && <section className="panel payroll-calculate-panel">
      <div className="panel-title-row"><div><h2>TÍNH BẢNG LƯƠNG</h2><p>Kỳ 1 là 01–15; Kỳ 2 là 16–cuối tháng. Tiền trách nhiệm Leader chỉ tự cộng ở Kỳ 2.</p></div></div>
      <div className="data-toolbar">
        <label>Tháng lương<input type="month" value={month} onChange={(event) => setMonth(event.target.value)} /></label>
        <label>Kỳ lương<select value={periodNo} onChange={(event) => setPeriodNo(Number(event.target.value))}><option value={1}>Kỳ 1</option><option value={2}>Kỳ 2</option></select></label>
        <label className="payroll-file">File TimeSoft<input type="file" accept=".xlsx" onChange={(event) => setFile(event.target.files?.[0] || null)} /></label>
        <button className="primary-button" onClick={calculate} disabled={busy === 'calculate'}><Upload size={16} /> {busy === 'calculate' ? 'Đang tính…' : 'Upload & tính lương'}</button>
      </div>
    </section>}

    {permissions.payroll_config_edit && <section className="panel">
      <div className="panel-title-row"><div><h2><Settings2 size={17} /> CÀI ĐẶT KHẤU TRỪ MẶC ĐỊNH</h2><p>Áp dụng khi tính bảng lương mới.</p></div><button className="primary-button" onClick={saveConfig} disabled={busy === 'config'}><Save size={16} /> Lưu cài đặt</button></div>
      <div className="payroll-config-grid">
        <label>Chi phí sinh hoạt<input type="number" min="0" value={config.default_living_expense} onChange={(event) => setConfig({ ...config, default_living_expense: Number(event.target.value) })} /></label>
        <label>Hỗ trợ Locker<input type="number" min="0" value={config.default_locker_support} onChange={(event) => setConfig({ ...config, default_locker_support: Number(event.target.value) })} /></label>
        <label>Tiền trách nhiệm Leader (Kỳ 2)<input type="number" min="0" value={config.leader_responsibility_allowance} onChange={(event) => setConfig({ ...config, leader_responsibility_allowance: Number(event.target.value) })} /></label>
      </div>
    </section>}

    {draft?.rows?.length > 0 && <section className="panel payroll-draft-panel">
      <div className="panel-title-row"><div><h2>{draft.period_label}</h2><p>{draft.rows.length} nhân viên · Tổng thực nhận {money(draftTotal)}</p></div><div className="list-actions">{permissions.payroll_save && <button className="primary-button" onClick={saveDraft} disabled={busy === 'save'}><Save size={16} /> Lưu kỳ lương</button>}{permissions.payroll_email && <button className="secondary-button" onClick={emailDraft} disabled={busy === 'email'}><Mail size={16} /> Gửi email ({selected.length})</button>}</div></div>
      <div className="responsive-data-table payroll-editor"><table><thead><tr><th>Gửi</th><th>Nhân viên</th><th>Lương</th>{Object.entries(EDIT_LABELS).map(([field, label]) => <th key={field}>{label}</th>)}<th>Thực nhận</th></tr></thead><tbody>{draft.rows.map((row) => <tr key={row['Tên Hệ thống']}><td className="center"><input type="checkbox" checked={selected.includes(row['Tên Hệ thống'])} onChange={() => setSelected((current) => current.includes(row['Tên Hệ thống']) ? current.filter((item) => item !== row['Tên Hệ thống']) : [...current, row['Tên Hệ thống']])} /></td><td><strong>{row['Tên Hệ thống']}</strong><small>{row['Họ và tên']}</small><small>{row.Email || 'Chưa có email'}</small></td><td className="money-cell">{money(row['Tiền Lương'])}</td>{Object.keys(EDIT_LABELS).map((field) => <td key={field}><input className="payroll-money-input" type="number" min="0" value={row[field] || 0} onChange={(event) => editMoney(row['Tên Hệ thống'], field, event.target.value)} /></td>)}<td className="money-cell"><strong>{money(row['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
    </section>}

    {permissions.payroll_penalty_obligation && <section className="panel">
      <div className="panel-title-row"><div><h2>NGHĨA VỤ VI PHẠM</h2><p>Khoản còn mở sẽ đưa vào “Vi phạm kỳ trước” từ ngày bắt đầu trừ.</p></div></div>
      <form className="payroll-obligation-form" onSubmit={addObligation}><label>Nhân viên<input required list="payroll-employee-options" value={obligationForm.employee_name} onChange={(event) => setObligationForm({ ...obligationForm, employee_name: event.target.value })} /></label><label>Số tiền<input required type="number" min="1" value={obligationForm.amount} onChange={(event) => setObligationForm({ ...obligationForm, amount: event.target.value })} /></label><label>Bắt đầu trừ từ<input required type="date" value={obligationForm.due_from} onChange={(event) => setObligationForm({ ...obligationForm, due_from: event.target.value })} /></label><label>Nội dung<input required value={obligationForm.content} onChange={(event) => setObligationForm({ ...obligationForm, content: event.target.value })} /></label><button className="primary-button" disabled={busy === 'obligation'}><Plus size={16} /> Thêm nghĩa vụ</button></form>
      <datalist id="payroll-employee-options">{Array.from(new Set([...(history.employees || []), ...(draft?.rows || []).map((row) => row['Tên Hệ thống'])])).map((name) => <option key={name}>{name}</option>)}</datalist>
      <div className="responsive-data-table"><table><thead><tr><th>Nhân viên</th><th>Số tiền</th><th>Bắt đầu trừ</th><th>Nội dung</th><th></th></tr></thead><tbody>{obligations.map((item) => <tr key={item.id}><td>{item.employee_name}</td><td>{money(item.amount)}</td><td>{item.due_from}</td><td>{item.content}</td><td><button className="danger-button compact" onClick={() => removeObligation(item.id)}><Trash2 size={14} /> Xóa</button></td></tr>)}</tbody></table></div>
      {!obligations.length && <div className="setup-note">Chưa có Nghĩa vụ vi phạm nhập từ Web V2.</div>}
    </section>}

    <section className="panel">
      <div className="panel-title-row"><div><h2>LỊCH SỬ BẢNG LƯƠNG</h2><p>Bộ lọc nhân viên dùng đối chiếu chính xác, không trộn dữ liệu người có tên gần giống.</p></div></div>
      <div className="data-toolbar"><label>Kỳ lương<select value={batch} onChange={(event) => setBatch(event.target.value)}><option value="">Tất cả kỳ lương</option>{history.batches.map((item) => <option key={item}>{item}</option>)}</select></label><label>Nhân viên<select value={employee} onChange={(event) => setEmployee(event.target.value)}><option value="">Tất cả nhân viên</option>{history.employees.map((item) => <option key={item}>{item}</option>)}</select></label>{permissions.payroll_export && <button className="secondary-button" onClick={() => veraApi.exportPayrollExcel(batch, employee)}><Download size={16} /> Export Excel</button>}</div>
      <div className="metric-grid small payroll-history-metrics"><div className="metric-card"><span>Số dòng lương</span><strong>{history.records.length}</strong></div><div className="metric-card"><span>Tổng thực nhận đang xem</span><strong>{money(historyTotal)}</strong></div></div>
      <div className="responsive-data-table"><table><thead><tr><th>Nhân viên</th><th>Kỳ lương</th><th>Lương</th><th>Hoàn trả tích lũy</th><th>Vi phạm</th><th>Nghĩa vụ cũ</th><th>Thực nhận</th></tr></thead><tbody>{history.records.map((item, index) => <tr key={`${item['Mã bản lưu']}-${item['Tên Hệ thống']}-${index}`}><td><strong>{item['Tên Hệ thống']}</strong><small>{item['Họ và tên']}</small></td><td>{item['Mã bản lưu'] || `${item['Từ ngày']} – ${item['Đến ngày']}`}</td><td>{money(item['Tiền Lương'])}</td><td>{money(item['Hoàn trả tiền tích lũy'])}</td><td>{money(item['Tiền phạt trong tháng'])}</td><td>{money(item['Vi phạm kỳ trước'])}</td><td><strong>{money(item['Số tiền thực nhận'])}</strong></td></tr>)}</tbody></table></div>
      {!history.records.length && <div className="setup-note">Không có bảng lương phù hợp.</div>}
    </section>
  </div>
}
