import { Download, Mail, Plus, RefreshCw, Save, Send, Settings2, Trash2 } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { getCurrentSession } from '../lib/supabase'
import { numberInputDisplayValue } from '../lib/numberInput'

const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const labels = { quanly: 'Quản lý', locker: 'Locker', letan: 'Lễ tân', tapvu: 'Tạp vụ' }
const money = (value) => Number(value || 0).toLocaleString('vi-VN') + 'đ'
const monthNow = () => {
  const now = new Date()
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, '0')}`
}

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
  ['violation_penalty', 'Phạt vi phạm'], ['late_penalty', 'Phạt đi trễ'], ['advance', 'Tiền đã ứng'],
]

const hourlyConfigFields = [
  ['rate_ca1', 'Lương giờ Ca 1'], ['rate_ca2_before_22', 'Ca 2 trước 22h'],
  ['rate_ca2_after_22', 'Ca 2 sau 22h'],
]

const monthlyConfigFields = [
  ['default_base_salary', 'Lương cơ bản mặc định'],
]

const sharedConfigFields = [
  ['standard_day_hours', 'Số giờ quy đổi 1 ngày'], ['full_day_hours', 'Số giờ đạt Full'],
  ['full_day_allowance', 'Phụ cấp mỗi ngày Full'],
  ['default_attendance_bonus', 'Chuyên cần mặc định'], ['default_responsibility', 'Trách nhiệm mặc định'],
  ['default_seniority', 'Thâm niên mặc định'], ['default_combo_sales', 'Bán combo mặc định'],
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

function sampleEmail(template, department, month, row) {
  const sample = row || { employee_name: 'Nguyễn Văn A', total_salary: 10000000, violation_penalty: 0, late_penalty: 50000, net_salary: 9950000 }
  const values = {
    ten_nhan_vien: sample.employee_name || sample.employee_username,
    bo_phan: labels[department], thang: month.split('-').reverse().join('/'),
    tong_luong: money(sample.total_salary),
    tong_phat: money(Number(sample.violation_penalty || 0) + Number(sample.late_penalty || 0)),
    thuc_nhan: money(sample.net_salary),
    bang_chi_tiet: 'Chi tiết các khoản lương và khấu trừ được đính kèm trong file Excel.',
  }
  const apply = (value) => Object.entries(values).reduce((text, [key, replacement]) => text.replaceAll(`{${key}}`, replacement), String(value || ''))
  return { subject: apply(template.subject), body: apply(template.body) }
}

export default function DepartmentPayrollPanel({ user, settingsOnly = false }) {
  const role = String(user?.role || '').toLowerCase()
  const isAdmin = role === 'admin'
  const permissions = user?.permissions || {}
  const canConfig = isAdmin && (permissions.payroll_config_edit !== false)
  const canSave = isAdmin || permissions.payroll_save
  const canExport = isAdmin || permissions.payroll_export
  const canEmail = isAdmin || permissions.payroll_email
  const [department, setDepartment] = useState('locker')
  const [month, setMonth] = useState(monthNow())
  const [settings, setSettings] = useState({})
  const [salaryConfigTables, setSalaryConfigTables] = useState({ operations: [], tapvu: [] })
  const [rows, setRows] = useState([])
  const [selected, setSelected] = useState([])
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const current = settings[department] || { config: {}, penalty_rules: [], email_template: { subject: '', body: '' } }
  const preview = useMemo(() => sampleEmail(current.email_template || {}, department, month, rows[0]), [current.email_template, department, month, rows])
  const totalNet = rows.reduce((sum, row) => sum + Number(row.net_salary || 0), 0)
  const visibleConfigFields = current.config.calculation_mode === 'monthly'
    ? [...monthlyConfigFields, ...sharedConfigFields]
    : [...hourlyConfigFields, ...sharedConfigFields]

  const run = async (key, callback) => {
    setBusy(key); setNotice(null)
    try { await callback() } catch (error) { setNotice({ type: 'error', message: error.message }) } finally { setBusy('') }
  }

  const loadSettings = async () => run('settings-load', async () => {
    const result = await request('/v2/department-payroll/settings')
    setSettings(result.departments || {})
    setSalaryConfigTables(result.salary_config_tables || { operations: [], tapvu: [] })
  })

  useEffect(() => { void loadSettings() }, []) // eslint-disable-line react-hooks/exhaustive-deps

  const updateCurrent = (patch) => setSettings((value) => ({ ...value, [department]: { ...current, ...patch } }))
  const updateConfig = (key, value) => updateCurrent({ config: { ...current.config, [key]: value } })
  const updateTemplate = (key, value) => updateCurrent({ email_template: { ...current.email_template, [key]: value } })
  const updateRule = (index, key, value) => updateCurrent({ penalty_rules: current.penalty_rules.map((item, itemIndex) => itemIndex === index ? { ...item, [key]: value } : item) })

  const saveSettings = () => run('settings-save', async () => {
    const result = await request(`/v2/department-payroll/settings/${department}`, {
      method: 'PUT', body: JSON.stringify({ config: current.config, penalty_rules: current.penalty_rules, email_template: current.email_template }),
    })
    setSettings((value) => ({ ...value, [department]: result }))
    setNotice({ type: 'success', message: result.message })
  })

  const calculate = () => run('calculate', async () => {
    const result = await request(`/v2/department-payroll/calculate?department=${department}&month=${month}`)
    setRows(result.rows || []); setSelected([])
    setSettings((value) => ({ ...value, [department]: result }))
    setNotice({ type: 'success', message: `Đã tính ${result.rows?.length || 0} nhân viên ${labels[department]} từ Chấm công và Lịch làm việc Web V2.` })
  })

  const loadDraft = () => run('draft-load', async () => {
    const result = await request(`/v2/department-payroll/draft?department=${department}&month=${month}`)
    if (!result.rows?.length) throw new Error('Kỳ này chưa có bảng lương nháp.')
    setRows(result.rows); setSelected([])
    setNotice({ type: 'success', message: `Đã mở bảng lương nháp ${labels[department]}.` })
  })

  const editRow = (employee, key, value) => setRows((items) => items.map((item) => item.employee_username === employee ? recalculate({ ...item, [key]: value }, current.config) : item))
  const payload = () => ({ department, month, rows })

  const saveDraft = () => run('draft-save', async () => {
    const result = await request('/v2/department-payroll/draft', { method: 'PUT', body: JSON.stringify(payload()) })
    setRows(result.rows); setNotice({ type: 'success', message: result.message })
  })
  const saveOfficial = () => run('official-save', async () => {
    if (!window.confirm(`Lưu chính thức bảng lương ${labels[department]} tháng ${month.split('-').reverse().join('/')}?`)) return
    const result = await request('/v2/department-payroll/save', { method: 'POST', body: JSON.stringify(payload()) })
    setRows(result.rows); setNotice({ type: 'success', message: result.message })
  })
  const exportExcel = () => run('export', async () => {
    const blob = await request('/v2/department-payroll/export.xlsx', { method: 'POST', body: JSON.stringify(payload()), download: true })
    const url = URL.createObjectURL(blob); const anchor = document.createElement('a')
    anchor.href = url; anchor.download = `Bang_luong_${department}_${month}.xlsx`; anchor.click()
    window.setTimeout(() => URL.revokeObjectURL(url), 1000)
  })
  const sendEmail = () => run('email', async () => {
    if (!selected.length) throw new Error('Vui lòng chọn nhân viên cần gửi email.')
    if (!window.confirm(`Gửi ${selected.length} email bảng lương ${labels[department]}?`)) return
    const result = await request('/v2/department-payroll/email', { method: 'POST', body: JSON.stringify({ ...payload(), employees: selected }) })
    setNotice({ type: result.ok ? 'success' : 'error', message: result.message })
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

  const employeeConfigTable = (group, title, fields) => {
    const items = salaryConfigTables[group] || []
    return <section className="department-config-table-section">
      <div className="panel-title-row"><div><h3>{title}</h3><p>Mỗi nhân viên là một dòng; mức đã lưu được dùng trực tiếp khi tính bảng lương tháng.</p></div></div>
      <div className="responsive-data-table department-config-table"><table>
        <thead><tr><th>TT</th><th>Nhân viên</th><th>Bộ phận</th>{fields.map(([, label]) => <th key={label}>{label}</th>)}</tr></thead>
        <tbody>{items.map((row, index) => <tr key={row.employee_username}>
          <td>{index + 1}</td>
          <td><strong>{row.employee_name}</strong><small>{row.employee_username}</small></td>
          <td><strong>{row.department_label}</strong></td>
          {fields.map(([key]) => <td key={key}><input className="payroll-money-input" type="number" min="0" inputMode="numeric" disabled={Boolean(busy)} value={numberInputDisplayValue(row[key])} onChange={(event) => editEmployeeConfig(group, row.employee_username, key, event.target.value)} /></td>)}
        </tr>)}</tbody>
      </table></div>
      {!items.length && <div className="setup-note">Chưa có nhân viên đang làm việc trong nhóm này.</div>}
    </section>
  }

  const settingsPanel = canConfig ? <div className="department-payroll-settings department-payroll-settings-standalone">
    <div className="payroll-calculation-mode">
      <strong>{current.config.calculation_mode === 'monthly' ? 'Lương cơ bản theo 26 ngày công' : 'Lương theo số giờ chấm công'}</strong>
      <span>{current.config.calculation_mode === 'monthly' ? 'Tiền lương = lương cơ bản × ngày công thực tế / ngày công chuẩn.' : 'Tiền lương = tổng số giờ từng ca × mức lương giờ tương ứng.'}</span>
    </div>
    <h3>CÔNG THỨC LƯƠNG {labels[department].toUpperCase()}</h3>
    <div className="payroll-config-grid">{visibleConfigFields.map(([key, label]) => <label key={key}>{label}<input type="number" min="0" value={numberInputDisplayValue(current.config[key])} onChange={(event) => updateConfig(key, Number(event.target.value))} /></label>)}</div>

    <div className="panel-title-row department-rule-title"><div><h3>BẢNG QUY ĐỊNH PHẠT RIÊNG</h3><p>Đang để trống để Admin nhập quy định sau. Chỉ các quy định bật mới được sử dụng.</p></div><button className="secondary-button" onClick={() => updateCurrent({ penalty_rules: [...current.penalty_rules, { id: crypto.randomUUID(), name: 'Quy định mới', amount: 0, note: '', enabled: true }] })}><Plus size={15} /> Thêm quy định</button></div>
    <div className="responsive-data-table"><table><thead><tr><th>Áp dụng</th><th>Tên quy định</th><th>Mức phạt</th><th>Ghi chú</th><th /></tr></thead><tbody>{current.penalty_rules.map((rule, index) => <tr key={rule.id}><td><input type="checkbox" checked={rule.enabled !== false} onChange={(event) => updateRule(index, 'enabled', event.target.checked)} /></td><td><input value={rule.name} onChange={(event) => updateRule(index, 'name', event.target.value)} /></td><td><input type="number" min="0" value={numberInputDisplayValue(rule.amount)} onChange={(event) => updateRule(index, 'amount', Number(event.target.value))} /></td><td><input value={rule.note || ''} onChange={(event) => updateRule(index, 'note', event.target.value)} /></td><td><button className="icon-button danger" onClick={() => updateCurrent({ penalty_rules: current.penalty_rules.filter((_, itemIndex) => itemIndex !== index) })}><Trash2 size={15} /></button></td></tr>)}</tbody></table></div>
    {!current.penalty_rules.length && <div className="setup-note">Chưa nhập quy định phạt cho {labels[department]}.</div>}

    <h3>MẪU EMAIL BẢNG LƯƠNG</h3>
    <div className="department-email-grid"><div><label>Tiêu đề<input value={current.email_template.subject || ''} onChange={(event) => updateTemplate('subject', event.target.value)} /></label><label>Nội dung<textarea rows="12" value={current.email_template.body || ''} onChange={(event) => updateTemplate('body', event.target.value)} /></label><small>Biến dùng được: {'{ten_nhan_vien}'}, {'{bo_phan}'}, {'{thang}'}, {'{tong_luong}'}, {'{tong_phat}'}, {'{thuc_nhan}'}, {'{bang_chi_tiet}'}</small></div><div className="department-email-preview"><strong>{preview.subject}</strong><pre>{preview.body}</pre></div></div>
    <button className="primary-button" disabled={Boolean(busy)} onClick={saveSettings}><Save size={16} /> Lưu mức lương, phụ cấp và mẫu email</button>
  </div> : <div className="error-box">Chỉ Admin được thay đổi cấu hình lương và phụ cấp.</div>

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
      <div className="panel-title-row"><div><h2>BẢNG LƯƠNG THÁNG THEO BỘ PHẬN</h2><p>Quản lý, Locker và Lễ tân tính theo giờ; Tạp vụ tính lương cơ bản theo 26 ngày công. Mỗi bộ phận có một bảng chính thức mỗi tháng; lưu lại cùng tháng sẽ cập nhật bảng tháng đó.</p></div></div>
      {notice && <div className={notice.type === 'error' ? 'error-box' : 'success-box'}>{notice.message}</div>}
      <div className="department-payroll-toolbar">
        <div className="department-payroll-tabs">{Object.entries(labels).map(([key, label]) => <button key={key} className={department === key ? 'primary-button' : 'secondary-button'} onClick={() => { setDepartment(key); setRows([]); setSelected([]) }}>{label}</button>)}</div>
        <label>Tháng lương<input type="month" value={month} onChange={(event) => { setMonth(event.target.value); setRows([]) }} /></label>
        <button className="primary-button" disabled={Boolean(busy)} onClick={calculate}><RefreshCw size={16} className={busy === 'calculate' ? 'spin' : ''} /> Tính từ chấm công</button>
        <button className="secondary-button" disabled={Boolean(busy)} onClick={loadDraft}>Mở bảng nháp</button>
      </div>

      {!!rows.length && <>
        <div className="department-payroll-summary"><span>Nhân viên<strong>{rows.length}</strong></span><span>Tổng thực nhận<strong>{money(totalNet)}</strong></span><span>Đã chọn gửi email<strong>{selected.length}</strong></span></div>
        {canEmail && <div className="list-actions"><button className="secondary-button" type="button" onClick={() => setSelected(rows.filter((row) => String(row.email || '').includes('@')).map((row) => row.employee_username))}><Mail size={15} /> Chọn tất cả có email</button><button className="secondary-button" type="button" onClick={() => setSelected([])}>Bỏ chọn</button></div>}
        <div className="responsive-data-table department-payroll-table"><table><thead><tr><th>Gửi</th><th>TT</th><th>Nhân viên</th><th>Ngày công</th><th>Giờ Ca 1</th><th>Ca 2 trước 22h</th><th>Ca 2 sau 22h</th><th>Tiền lương</th>{editableFields.map(([, label]) => <th key={label}>{label}</th>)}<th>Tổng lương</th><th>Thực nhận</th></tr></thead><tbody>{rows.map((row) => <tr key={row.employee_username}><td><input type="checkbox" checked={selected.includes(row.employee_username)} onChange={() => setSelected((items) => items.includes(row.employee_username) ? items.filter((item) => item !== row.employee_username) : [...items, row.employee_username])} /></td><td>{row.tt}</td><td><strong>{row.employee_name}</strong><small>{row.employee_username} · {row.email || 'Chưa có email'}</small>{row.incomplete_days > 0 && <small className="attendance-warning">{row.incomplete_days} ngày thiếu đủ FaceID</small>}</td><td>{row.work_days}</td><td>{row.hours_ca1}</td><td>{row.hours_ca2_before_22}</td><td>{row.hours_ca2_after_22}</td><td className="money-cell">{money(row.salary)}</td>{editableFields.map(([key]) => <td key={key}><input className="payroll-money-input" type="number" min="0" value={numberInputDisplayValue(row[key])} onChange={(event) => editRow(row.employee_username, key, event.target.value)} /></td>)}<td className="money-cell"><strong>{money(row.total_salary)}</strong></td><td className="money-cell"><strong>{money(row.net_salary)}</strong></td></tr>)}</tbody></table></div>
        <div className="list-actions department-payroll-actions">{canSave && <button className="secondary-button" disabled={Boolean(busy)} onClick={saveDraft}><Save size={16} /> Lưu bảng nháp</button>}{canSave && <button className="primary-button" disabled={Boolean(busy)} onClick={saveOfficial}><Save size={16} /> Lưu chính thức</button>}{canExport && <button className="secondary-button" disabled={Boolean(busy)} onClick={exportExcel}><Download size={16} /> Export Excel</button>}{canEmail && <button className="secondary-button" disabled={Boolean(busy) || !selected.length} onClick={sendEmail}><Send size={16} /> <Mail size={14} /> Gửi email ({selected.length})</button>}</div>
      </>}
    </section>
  </div>
}
