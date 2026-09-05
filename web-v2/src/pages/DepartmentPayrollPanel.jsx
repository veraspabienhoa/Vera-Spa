import { Banknote, CalendarDays, CheckCircle2, Download, History, Mail, Plus, RefreshCw, Save, Search, Send, Settings2, Trash2 } from 'lucide-react'
import { useEffect, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'
import { numberInputDisplayValue } from '../lib/numberInput'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const labels = { quanly: 'Quản lý', locker: 'Locker', letan: 'Lễ tân', tapvu: 'Tạp vụ' }
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const monthNow = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}
const normalizeSearch = (value) => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replaceAll('đ', 'd').toLowerCase().trim()

async function request(path, options = {}) {
  if (!apiBase) throw new Error('Python API V2 chưa được cấu hình.')
  const session = await getCurrentSession()
  const headers = new Headers(options.headers || {})
  if (options.body && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json')
  if (session?.access_token) headers.set('Authorization', `Bearer ${session.access_token}`)
  const response = await fetch(`${apiBase}${path}`, { ...options, headers })
  if (options.download) {
    if (!response.ok) {
      const payload = await response.json().catch(() => ({}))
      throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
    }
    return response.blob()
  }
  const payload = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}

function recalculate(source, config) {
  const row = { ...source }
  const number = (key) => Math.max(0, Number(row[key] || 0))
  const salary = config.calculation_mode === 'monthly'
    ? Math.round(number('base_salary') * number('work_days') / Math.max(1, Number(config.standard_month_days || 26)))
    : Math.round(
      number('hours_ca1') * Number(config.rate_ca1 || 0)
      + number('hours_ca2_before_22') * Number(config.rate_ca2_before_22 || 0)
      + number('hours_ca2_after_22') * Number(config.rate_ca2_after_22 || 0),
    )
  row.salary = salary
  row.total_salary = salary + ['full_allowance', 'attendance_bonus', 'responsibility', 'seniority', 'combo_sales', 'other_income_1', 'other_income_2'].reduce((sum, key) => sum + number(key), 0)
  row.net_salary = row.total_salary - ['violation_penalty', 'late_penalty', 'advance'].reduce((sum, key) => sum + number(key), 0)
  return row
}

const editableFields = [
  ['base_salary', 'Lương cơ bản'], ['full_allowance', 'Phụ cấp Full'],
  ['attendance_bonus', 'Chuyên cần'], ['responsibility', 'Trách nhiệm'],
  ['seniority', 'Thâm niên'], ['combo_sales', 'Bán combo'],
  ['other_income_1', 'Khoản cộng 1'], ['other_income_2', 'Khoản cộng 2'],
  ['violation_penalty', 'Phạt vi phạm'], ['late_penalty', 'Phạt đi trễ'],
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
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const permissions = user?.permissions || {}
  const canConfig = isAdmin && (permissions.payroll_config_edit !== false)
  const canSave = isAdmin || permissions.payroll_save
  const canExport = isAdmin || permissions.payroll_export
  const canEmail = isAdmin || permissions.payroll_email
  const [month, setMonth] = useState(monthNow())
  const [settings, setSettings] = useState({})
  const [salaryConfigTables, setSalaryConfigTables] = useState({ operations: [], tapvu: [] })
  const [employeeCatalog, setEmployeeCatalog] = useState([])
  const [addDepartment, setAddDepartment] = useState('quanly')
  const [employeeSearch, setEmployeeSearch] = useState({ operations: '', tapvu: '' })
  const [pendingEmployee, setPendingEmployee] = useState({ operations: '', tapvu: '' })
  const [rows, setRows] = useState([])
  const [history, setHistory] = useState([])
  const [editingHistoryId, setEditingHistoryId] = useState('')
  const [selected, setSelected] = useState([])
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const totalNet = rows.reduce((sum, row) => sum + Number(row.net_salary || 0), 0)
  const totalAdvance = rows.reduce((sum, row) => sum + Number(row.advance || 0), 0)

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { await callback() } catch (error) { setNotice({ type: 'error', message: error.message }) } finally { setBusy('') }
  }

  const loadSettings = async () => run('settings-load', async () => {
    const [result, historyResult] = await Promise.all([
      request('/v2/department-payroll/settings'),
      settingsOnly ? Promise.resolve({ items: [] }) : request('/v2/department-payroll/combined/history'),
    ])
    setSettings(result.departments || {})
    setSalaryConfigTables(result.salary_config_tables || { operations: [], tapvu: [] })
    setEmployeeCatalog(result.salary_employee_catalog || [])
    setHistory(historyResult.items || [])
  })

  useEffect(() => { void loadSettings() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const calculate = (source) => run(`calculate-${source}`, async () => {
    const result = await request(`/v2/department-payroll/combined/calculate?month=${month}&source=${source}`)
    setRows(result.rows || []); setSelected([])
    setEditingHistoryId('')
    setNotice({ type: 'success', message: `Đã tính ${result.rows?.length || 0} nhân viên Quản lý, Locker, Lễ tân và Tạp vụ từ ${result.source_label}.` })
  })

  const loadDraft = () => run('draft-load', async () => {
    const result = await request(`/v2/department-payroll/combined/draft?month=${month}`)
    if (!result.rows?.length) throw new Error('Kỳ này chưa có bảng lương nháp.')
    setRows(result.rows); setSelected([])
    setEditingHistoryId('')
    setNotice({ type: 'success', message: 'Đã mở bảng Lương hành chánh nháp.' })
  })

  const editRow = (employee, key, value) => setRows((items) => items.map((item) => item.employee_username === employee
    ? recalculate({ ...item, [key]: value }, item.calculation_config || settings[item.department]?.config || {})
    : item))
  const payload = () => ({ month, rows, history_id: editingHistoryId })

  const saveDraft = () => run('draft-save', async () => {
    const result = await request('/v2/department-payroll/combined/draft', { method: 'PUT', body: JSON.stringify(payload()) })
    setRows(result.rows); setNotice({ type: 'success', message: result.message })
  })
  const completePayroll = () => run('complete', async () => {
    if (!window.confirm(`Hoàn thành bảng Lương hành chánh tháng ${month.split('-').reverse().join('/')} và lưu vào lịch sử?`)) return
    const result = await request('/v2/department-payroll/combined/complete', { method: 'POST', body: JSON.stringify(payload()) })
    setRows(result.rows); setEditingHistoryId(result.history_id || '')
    const historyResult = await request('/v2/department-payroll/combined/history')
    setHistory(historyResult.items || [])
    setNotice({ type: 'success', message: result.message })
  })
  const exportExcel = () => run('export', async () => {
    const blob = await request('/v2/department-payroll/combined/export.xlsx', { method: 'POST', body: JSON.stringify(payload()), download: true })
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `Luong_hanh_chanh_${month}.xlsx`; anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
  const sendEmail = () => run('email', async () => {
    if (!selected.length) throw new Error('Vui lòng chọn nhân viên cần gửi email.')
    if (!window.confirm(`Gửi ${selected.length} email bảng Lương hành chánh?`)) return
    const results = []
    for (const department of Object.keys(labels)) {
      const departmentRows = rows.filter((row) => row.department === department && selected.includes(row.employee_username))
      if (departmentRows.length) results.push(await request('/v2/department-payroll/email', {
        method: 'POST',
        body: JSON.stringify({ department, month, rows: rows.filter((row) => row.department === department), employees: departmentRows.map((row) => row.employee_username) }),
      }))
    }
    const sent = results.reduce((sum, item) => sum + (item.sent?.length || 0), 0)
    const failed = results.reduce((sum, item) => sum + (item.failed?.length || 0), 0)
    setNotice({ type: failed ? 'error' : 'success', message: `Đã gửi ${sent} email; lỗi ${failed}.` })
  })

  const openHistory = (historyId) => run('history-open', async () => {
    const result = await request(`/v2/department-payroll/combined/history/${encodeURIComponent(historyId)}/open`, { method: 'POST' })
    setMonth(result.month); setRows(result.rows || []); setSelected([]); setEditingHistoryId(result.history_id)
    setNotice({ type: 'success', message: result.message })
  })

  const editEmployeeConfig = (group, username, key, value) => setSalaryConfigTables((currentTables) => ({
    ...currentTables,
    [group]: (currentTables[group] || []).map((row) => row.employee_username === username ? { ...row, [key]: Number(value) } : row),
  }))

  const saveEmployeeConfigs = () => run('employee-settings-save', async () => {
    const result = await request('/v2/department-payroll/settings/employees', {
      method: 'PUT',
      body: JSON.stringify({ rows: [...(salaryConfigTables.operations || []), ...(salaryConfigTables.tapvu || [])] }),
    })
    setSalaryConfigTables(result.salary_config_tables || salaryConfigTables)
    setNotice({ type: 'success', message: result.message })
  })

  const employeeCandidates = (group) => {
    const departments = group === 'tapvu' ? new Set(['tapvu']) : new Set([addDepartment])
    const configured = new Set([...(salaryConfigTables.operations || []), ...(salaryConfigTables.tapvu || [])].map((row) => row.employee_username))
    const search = normalizeSearch(employeeSearch[group])
    return employeeCatalog.filter((item) => departments.has(item.department)
      && !configured.has(item.employee_username)
      && (!search || normalizeSearch(`${item.employee_name} ${item.employee_username}`).includes(search)))
  }

  const addEmployeeRow = (group) => {
    const username = pendingEmployee[group]
    const candidate = employeeCatalog.find((item) => item.employee_username === username)
    if (!candidate) {
      setNotice({ type: 'error', message: 'Vui lòng tìm và chọn một nhân viên trong đúng bộ phận.' })
      return
    }
    const config = settings[candidate.department]?.config || {}
    setSalaryConfigTables((tables) => ({ ...tables, [group]: [...(tables[group] || []), { ...config, ...candidate }] }))
    setPendingEmployee((value) => ({ ...value, [group]: '' }))
    setEmployeeSearch((value) => ({ ...value, [group]: '' }))
    setNotice(null)
  }

  const removeEmployeeRow = (group, username) => setSalaryConfigTables((tables) => ({
    ...tables, [group]: (tables[group] || []).filter((row) => row.employee_username !== username),
  }))

  const employeeConfigTable = (group, title, fields) => {
    const items = salaryConfigTables[group] || []
    const candidates = employeeCandidates(group)
    return <section className="department-config-table-section">
      <div className="panel-title-row"><div><h3>{title}</h3><p>Mỗi nhân viên là một dòng; mức đã lưu được dùng trực tiếp khi tính bảng lương tháng.</p></div></div>
      <div className="department-config-add-row">
        {group === 'operations' && <label>Bộ phận<select value={addDepartment} onChange={(event) => { setAddDepartment(event.target.value); setPendingEmployee((value) => ({ ...value, operations: '' })) }}><option value="quanly">Quản lý</option><option value="letan">Lễ tân</option><option value="locker">Locker</option></select></label>}
        <label className="department-config-search"><span>Tìm nhân viên</span><div><Search size={16} /><input value={employeeSearch[group]} placeholder="Nhập tên hoặc tên đăng nhập…" onChange={(event) => { setEmployeeSearch((value) => ({ ...value, [group]: event.target.value })); setPendingEmployee((value) => ({ ...value, [group]: '' })) }} /></div></label>
        <label>Chọn nhân viên<select value={pendingEmployee[group]} onChange={(event) => setPendingEmployee((value) => ({ ...value, [group]: event.target.value }))}><option value="">-- Chọn nhân viên --</option>{candidates.map((item) => <option key={item.employee_username} value={item.employee_username}>{item.employee_name} · {item.employee_username}</option>)}</select></label>
        <button className="secondary-button" type="button" disabled={Boolean(busy) || !pendingEmployee[group]} onClick={() => addEmployeeRow(group)}><Plus size={16} /> Thêm dòng</button>
      </div>
      <div className="responsive-data-table department-config-table"><table>
        <thead><tr><th>TT</th><th>Nhân viên</th><th>Bộ phận</th>{fields.map(([, label]) => <th key={label}>{label}</th>)}<th /></tr></thead>
        <tbody>{items.map((row, index) => <tr key={row.employee_username}>
          <td>{index + 1}</td>
          <td><strong>{row.employee_name}</strong><small>{row.employee_username}</small></td>
          <td><strong>{row.department_label}</strong></td>
          {fields.map(([key]) => <td key={key}><input className="payroll-money-input" type="number" min="0" inputMode="numeric" disabled={Boolean(busy)} value={numberInputDisplayValue(row[key])} onChange={(event) => editEmployeeConfig(group, row.employee_username, key, event.target.value)} /></td>)}
          <td><button className="icon-button danger" type="button" title="Xóa dòng cấu hình" disabled={Boolean(busy)} onClick={() => removeEmployeeRow(group, row.employee_username)}><Trash2 size={15} /></button></td>
        </tr>)}</tbody>
      </table></div>
      {!items.length && <div className="setup-note">Chưa có nhân viên đang làm việc trong nhóm này.</div>}
    </section>
  }

  if (settingsOnly) return <div className="feature-page department-payroll-page department-payroll-config-page">
    <section className="panel department-payroll-panel">
      <div className="panel-title-row"><div><h2><Settings2 size={18} /> CẤU HÌNH LƯƠNG THEO NHÂN VIÊN</h2><p>Quản lý, Lễ tân và Locker dùng chung bảng thứ nhất. Tạp vụ nằm ở bảng thứ hai bên dưới.</p></div><button className="secondary-button" type="button" onClick={loadSettings} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'settings-load' ? 'spin' : ''} /> Làm mới</button></div>
      {notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}
      {employeeConfigTable('operations', 'BẢNG 1 · QUẢN LÝ / LỄ TÂN / LOCKER', operationsEmployeeFields)}
      {employeeConfigTable('tapvu', 'BẢNG 2 · TẠP VỤ', tapvuEmployeeFields)}
      <div className="setup-note">Email bảng lương của bốn bộ phận dùng cùng mẫu chuẩn đang áp dụng cho Leader/Nhân viên.</div>
      {canConfig ? <div className="list-actions department-payroll-actions"><button className="primary-button" type="button" disabled={Boolean(busy)} onClick={saveEmployeeConfigs}><Save size={16} /> {busy === 'employee-settings-save' ? 'Đang lưu…' : 'Lưu toàn bộ cấu hình'}</button></div> : <div className="error-box">Chỉ Admin được thay đổi cấu hình lương và phụ cấp.</div>}
    </section>
  </div>

  return <div className="feature-page department-payroll-page">
    <section className="panel department-payroll-panel">
      <div className="panel-title-row"><div><h2>LƯƠNG HÀNH CHÁNH</h2><p>Một bảng chung cho Quản lý, Locker, Lễ tân và Tạp vụ. Quản lý/Locker/Lễ tân tính theo giờ; Tạp vụ tính theo 26 ngày công.</p></div></div>
      {notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}
      <div className="department-payroll-toolbar">
        <label>Tháng lương<input type="month" value={month} onChange={(event) => { setMonth(event.target.value); setRows([]); setEditingHistoryId('') }} /></label>
        <button className="secondary-button" disabled={Boolean(busy)} onClick={() => calculate('attendance')}><RefreshCw size={16} className={busy === 'calculate-attendance' ? 'spin' : ''} /> Tính từ chấm công</button>
        <button className="primary-button" disabled={Boolean(busy)} onClick={() => calculate('schedule')}><CalendarDays size={16} /> Tính từ lịch làm việc</button>
        <button className="secondary-button" disabled={Boolean(busy)} onClick={loadDraft}>Mở bảng nháp</button>
      </div>

      {!!rows.length && <>
        {editingHistoryId && <div className="setup-note"><History size={16} /> Đang sửa bảng lương đã lưu. Khi bấm Hoàn thành bảng lương, bản lịch sử này sẽ được cập nhật và giữ nguyên mã.</div>}
        <div className="department-payroll-summary"><span>Nhân viên<strong>{rows.length}</strong></span><span>Tổng ứng lương<strong>{money(totalAdvance)}</strong></span><span>Tổng thực nhận<strong>{money(totalNet)}</strong></span></div>
        <section className="salary-advance-panel">
          <div className="panel-title-row"><div><h3><Banknote size={17} /> NHÂN VIÊN ỨNG LƯƠNG</h3><p>Nhập số tiền đã ứng; hệ thống tự trừ ngay vào Thực nhận của bảng lương hiện tại.</p></div></div>
          <div className="salary-advance-grid">{rows.map((row) => <label key={`advance-${row.employee_username}`}><span>{row.employee_name}<small>{row.department_label}</small></span><input className="payroll-money-input" type="number" min="0" inputMode="numeric" value={numberInputDisplayValue(row.advance)} onChange={(event) => editRow(row.employee_username, 'advance', event.target.value)} /></label>)}</div>
        </section>
        {canEmail && <div className="list-actions"><button className="secondary-button" type="button" onClick={() => setSelected(rows.filter((row) => String(row.email || '').includes('@')).map((row) => row.employee_username))}><Mail size={15} /> Chọn tất cả có email</button><button className="secondary-button" type="button" onClick={() => setSelected([])}>Bỏ chọn</button></div>}
        <div className="responsive-data-table department-payroll-table"><table><thead><tr><th>Gửi</th><th>TT</th><th>Nhân viên</th><th>Bộ phận</th><th>Nguồn</th><th>Ngày công</th><th>Giờ Ca 1</th><th>Ca 2 trước 22h</th><th>Ca 2 sau 22h</th><th>Tiền lương</th>{editableFields.map(([, label]) => <th key={label}>{label}</th>)}<th>Tổng lương</th><th>Thực nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.employee_username}><td><input type="checkbox" checked={selected.includes(row.employee_username)} onChange={() => setSelected((items) => items.includes(row.employee_username) ? items.filter((item) => item !== row.employee_username) : [...items, row.employee_username])} /></td><td>{row.tt}</td><td><strong>{row.employee_name}</strong><small>{row.employee_username} · {row.email || 'Chưa có email'}</small>{row.incomplete_days > 0 && <small className="attendance-warning">{row.incomplete_days} ngày thiếu đủ FaceID</small>}</td><td><strong>{row.department_label}</strong></td><td>{row.calculation_source === 'schedule' ? 'Lịch làm việc' : 'Chấm công'}</td><td>{row.work_days}</td><td>{row.hours_ca1}</td><td>{row.hours_ca2_before_22}</td><td>{row.hours_ca2_after_22}</td><td className="money-cell">{money(row.salary)}</td>{editableFields.map(([key]) => <td key={key}><input className="payroll-money-input" type="number" min="0" value={numberInputDisplayValue(row[key])} onChange={(event) => editRow(row.employee_username, key, event.target.value)} /></td>)}<td className="money-cell"><strong>{money(row.total_salary)}</strong></td><td className="money-cell"><strong>{money(row.net_salary)}</strong></td></tr>)}</tbody></table></div>
        <div className="list-actions department-payroll-actions">{canSave && <button className="secondary-button" disabled={Boolean(busy)} onClick={saveDraft}><Save size={16} /> Lưu bảng nháp</button>}{canSave && <button className="primary-button" disabled={Boolean(busy)} onClick={completePayroll}><CheckCircle2 size={16} /> Hoàn thành bảng lương</button>}{canExport && <button className="secondary-button" disabled={Boolean(busy)} onClick={exportExcel}><Download size={16} /> Export Excel</button>}{canEmail && <button className="secondary-button" disabled={Boolean(busy) || !selected.length} onClick={sendEmail}><Send size={16} /> <Mail size={14} /> Gửi email ({selected.length})</button>}</div>
      </>}
    </section>
    <section className="panel department-payroll-history">
      <div className="panel-title-row"><div><h2><History size={18} /> LỊCH SỬ BẢNG LƯƠNG</h2><p>Bảng đã hoàn thành có thể mở lại, chỉnh sửa và hoàn thành lại để cập nhật đúng bản cũ.</p></div><button className="secondary-button" type="button" onClick={loadSettings} disabled={Boolean(busy)}><RefreshCw size={16} /> Làm mới</button></div>
      <div className="department-history-list">{history.map((item) => <article key={item.id}><div><strong>Tháng {item.month_label}</strong><span>{item.employee_count} nhân viên · {item.source_label || 'Chấm công'} · Thực nhận {money(item.total_net)}</span><small>Lưu bởi {item.saved_by || '—'} · {item.saved_at ? new Date(item.saved_at).toLocaleString('vi-VN') : '—'}</small></div>{canSave && <button className="secondary-button" type="button" disabled={Boolean(busy)} onClick={() => openHistory(item.id)}><History size={15} /> Mở để sửa</button>}</article>)}</div>
      {!history.length && <div className="setup-note">Chưa có lịch sử bảng Lương hành chánh.</div>}
    </section>
  </div>
}
