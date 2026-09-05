import { Download, FileSignature, RefreshCw, Save, Search, Settings2, Users } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { contractApi } from '../lib/contractApi'

const scopeOptions = [
  { value: 'individual', label: 'Một nhân viên' },
  { value: 'department', label: 'Theo bộ phận' },
  { value: 'all', label: 'Tất cả Leader và nhân viên' },
]

const settingFields = [
  ['representative_name', 'Người đại diện'],
  ['representative_title', 'Chức vụ người đại diện'],
  ['business_name', 'Tên cơ sở'],
  ['business_address', 'Địa chỉ cơ sở'],
  ['contract_term', 'Thời hạn hợp đồng'],
  ['contract_effective', 'Hiệu lực hợp đồng'],
  ['signing_place', 'Địa điểm ký hợp đồng'],
  ['signing_date', 'Ngày ký hợp đồng'],
  ['salary_amount', 'Mức lương'],
  ['salary_unit', 'Đơn vị lương'],
]

const placeholderHelp = [
  '{{employee_name}}', '{{birth_day}}', '{{birth_month}}', '{{birth_year}}', '{{birth_place}}',
  '{{permanent_address}}', '{{cccd_number}}', '{{cccd_issue_date}}', '{{cccd_issue_place}}',
  '{{representative_name}}', '{{representative_title}}', '{{business_name}}', '{{business_address}}',
  '{{contract_term}}', '{{contract_effective}}', '{{sign_day}}', '{{sign_month}}', '{{sign_year}}', '{{salary}}',
]

export default function ContractPage() {
  const [data, setData] = useState(null)
  const [settings, setSettings] = useState(null)
  const [scope, setScope] = useState('individual')
  const [username, setUsername] = useState('')
  const [role, setRole] = useState('leader')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const load = async () => {
    setBusy('load'); setNotice(null)
    try {
      const result = await contractApi.overview()
      setData(result); setSettings(result.settings)
      const first = result.employees?.[0]?.username || ''
      setUsername((current) => result.employees?.some((item) => item.username === current) ? current : first)
      if (!result.permissions?.can_export_bulk) setScope('individual')
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }
  useEffect(() => { void load() }, [])

  const filteredEmployees = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('vi')
    if (!needle) return data?.employees || []
    return (data?.employees || []).filter((item) => `${item.full_name} ${item.username} ${item.role_label}`.toLocaleLowerCase('vi').includes(needle))
  }, [data?.employees, search])

  const exportCount = scope === 'individual'
    ? (username ? 1 : 0)
    : scope === 'department'
      ? (data?.employees || []).filter((item) => item.role === role).length
      : (data?.employees || []).length

  const save = async () => {
    setBusy('save'); setNotice(null)
    try {
      const result = await contractApi.saveSettings({ ...settings, expected_revision: data.revision })
      setData((current) => ({ ...current, settings: result.settings, revision: result.revision }))
      setSettings(result.settings)
      setNotice({ type: 'success', message: result.message })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  const exportContracts = async () => {
    setBusy('export'); setNotice(null)
    try {
      const result = await contractApi.exportPdf({ scope, username, role: scope === 'department' ? role : null })
      setNotice({ type: 'success', message: `Đã xuất ${result.count || exportCount} hợp đồng PDF.` })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  const permissions = data?.permissions || {}
  const canExport = scope === 'individual'
    ? (permissions.can_export_self || permissions.can_export_bulk)
    : permissions.can_export_bulk
  const canConfigure = permissions.can_edit_settings || permissions.can_edit_template

  return <div className="feature-page contract-page">
    <div className="page-heading">
      <div><span className="eyebrow"><FileSignature size={14} /> Hồ sơ lao động</span><h1>HỢP ĐỒNG SỐ 1</h1><p>Xuất hợp đồng bán thời gian cho từng nhân viên, theo bộ phận hoặc toàn bộ Leader và nhân viên.</p></div>
      <button className="secondary-button" onClick={load} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button>
    </div>

    {notice && <div className={notice.type === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}

    <section className="panel contract-export-panel">
      <div className="panel-title-row"><div><h2><Users size={18} /> Chọn đối tượng xuất hợp đồng</h2><p>Thông tin người lao động được lấy từ hồ sơ; địa chỉ thường trú ưu tiên dữ liệu đọc từ CCCD.</p></div><span className="contract-count">{exportCount} hợp đồng</span></div>
      {permissions.can_export_bulk && <div className="contract-scope-tabs">
        {scopeOptions.map((item) => <button type="button" key={item.value} className={scope === item.value ? 'active' : ''} onClick={() => setScope(item.value)}>{item.label}</button>)}
      </div>}
      {scope === 'individual' && <div className="contract-employee-picker">
        {permissions.can_export_bulk && <label className="contract-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm tên hoặc tài khoản nhân viên…" /></label>}
        <label>Nhân viên<select value={username} onChange={(event) => setUsername(event.target.value)}>{filteredEmployees.map((item) => <option key={item.username} value={item.username}>{item.full_name} · {item.role_label}</option>)}</select></label>
      </div>}
      {scope === 'department' && <label className="contract-department">Bộ phận<select value={role} onChange={(event) => setRole(event.target.value)}>{(data?.roles || []).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>}
      {scope === 'all' && <div className="contract-all-note">File PDF sẽ gồm hợp đồng của toàn bộ Leader và nhân viên đang làm việc, đang hiển thị trong hệ thống.</div>}
      <div className="contract-export-actions">
        <button className="primary-button" onClick={exportContracts} disabled={Boolean(busy) || !canExport || exportCount < 1}><Download size={17} /> {busy === 'export' ? 'Đang tạo PDF…' : `Xuất ${exportCount || ''} hợp đồng PDF`}</button>
        {!canExport && <small>Tài khoản chưa được cấp quyền xuất hợp đồng tương ứng.</small>}
      </div>
    </section>

    {canConfigure && settings && <section className="panel contract-settings-panel">
      <div className="panel-title-row"><div><h2><Settings2 size={18} /> Cài đặt Hợp đồng số 1</h2><p>Thay đổi thông tin người đại diện, thời hạn, ngày ký, mức lương và nội dung mẫu.</p></div></div>
      <div className="contract-settings-grid">
        {settingFields.map(([key, label]) => <label key={key} className={key === 'business_address' ? 'span-2' : ''}>{label}<input type={key === 'signing_date' ? 'date' : 'text'} value={settings[key] || ''} disabled={!permissions.can_edit_settings} onChange={(event) => setSettings({ ...settings, [key]: event.target.value })} /></label>)}
      </div>
      <label className="contract-template-field">Nội dung mẫu hợp đồng<textarea rows="20" value={settings.template_content || ''} disabled={!permissions.can_edit_template} onChange={(event) => setSettings({ ...settings, template_content: event.target.value })} /></label>
      <details className="contract-placeholders"><summary>Biến tự động có thể dùng trong mẫu</summary><div>{placeholderHelp.map((item) => <code key={item}>{item}</code>)}</div></details>
      <div className="contract-save-actions"><button className="primary-button" onClick={save} disabled={Boolean(busy)}><Save size={17} /> {busy === 'save' ? 'Đang lưu…' : 'Lưu cài đặt hợp đồng'}</button></div>
    </section>}
  </div>
}
