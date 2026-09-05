import { CheckSquare, Download, FileSignature, RefreshCw, Save, Search, Settings2, Square, Users } from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { contractApi } from '../lib/contractApi'
import VeraDateInput from '../components/VeraDateInput'

const scopeOptions = [
  { value: 'selected', label: 'Chọn nhân viên' },
  { value: 'department', label: 'Theo bộ phận' },
  { value: 'all', label: 'Tất cả nhân viên phù hợp' },
]

const fallbackContractTypes = [
  { value: 'ktv', label: 'Hợp đồng KTV', roles: ['leader', 'nhanvien'] },
  { value: 'letan', label: 'Hợp đồng Lễ tân', roles: ['letan'] },
  { value: 'locker', label: 'Hợp đồng Locker', roles: ['locker'] },
  { value: 'quanly', label: 'Hợp đồng Quản lý', roles: ['quanly'] },
  { value: 'tapvu', label: 'Hợp đồng Tạp vụ', roles: ['tapvu'] },
]

const contractTypeByRole = {
  leader: 'ktv',
  nhanvien: 'ktv',
  letan: 'letan',
  locker: 'locker',
  quanly: 'quanly',
  tapvu: 'tapvu',
}

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

export default function ContractPage({ user }) {
  const initialContractType = contractTypeByRole[String(user?.role || '').toLowerCase()] || 'ktv'
  const [contractType, setContractType] = useState(initialContractType)
  const [data, setData] = useState(null)
  const [settings, setSettings] = useState(null)
  const [scope, setScope] = useState('selected')
  const [selectedUsernames, setSelectedUsernames] = useState([])
  const [role, setRole] = useState('leader')
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState('')
  const [notice, setNotice] = useState(null)

  const load = useCallback(async (requestedType) => {
    setBusy('load'); setNotice(null)
    try {
      const result = await contractApi.overview(requestedType)
      setData(result); setSettings(result.settings)
      setContractType(result.contract_type || requestedType)
      const available = new Set((result.employees || []).map((item) => item.username))
      setSelectedUsernames((current) => {
        const retained = current.filter((username) => available.has(username))
        return retained.length ? retained : (result.employees?.[0]?.username ? [result.employees[0].username] : [])
      })
      setRole((current) => (result.roles || []).some((item) => item.value === current)
        ? current
        : (result.roles?.[0]?.value || ''))
      if (!result.permissions?.can_export_bulk) setScope('selected')
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }, [])
  useEffect(() => { void load(initialContractType) }, [initialContractType, load])

  const selectContractType = (value) => {
    if (value === contractType || busy) return
    setScope('selected')
    setSearch('')
    setSelectedUsernames([])
    void load(value)
  }

  const filteredEmployees = useMemo(() => {
    const needle = search.trim().toLocaleLowerCase('vi')
    if (!needle) return data?.employees || []
    return (data?.employees || []).filter((item) => `${item.full_name} ${item.username} ${item.role_label}`.toLocaleLowerCase('vi').includes(needle))
  }, [data?.employees, search])

  const selectedSet = useMemo(() => new Set(selectedUsernames), [selectedUsernames])
  const exportCount = scope === 'selected'
    ? selectedUsernames.length
    : scope === 'department'
      ? (data?.employees || []).filter((item) => item.role === role).length
      : (data?.employees || []).length

  const toggleEmployee = (username) => {
    setSelectedUsernames((current) => current.includes(username)
      ? current.filter((item) => item !== username)
      : [...current, username])
  }
  const selectFiltered = () => setSelectedUsernames((current) => [...new Set([...current, ...filteredEmployees.map((item) => item.username)])])
  const clearSelected = () => setSelectedUsernames([])

  const save = async () => {
    setBusy('save'); setNotice(null)
    try {
      const result = await contractApi.saveSettings({ ...settings, contract_type: contractType, expected_revision: data.revision })
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
      const result = await contractApi.exportPdf({
        contract_type: contractType,
        scope,
        usernames: scope === 'selected' ? selectedUsernames : [],
        role: scope === 'department' ? role : null,
      })
      setNotice({ type: 'success', message: `Đã xuất ${result.count || exportCount} ${data?.contract_label || 'hợp đồng'}.` })
    } catch (error) {
      setNotice({ type: 'error', message: error.message })
    } finally {
      setBusy('')
    }
  }

  const permissions = data?.permissions || {}
  const canExport = scope === 'selected'
    ? (permissions.can_export_self || permissions.can_export_bulk)
    : permissions.can_export_bulk
  const canConfigure = permissions.can_edit_settings || permissions.can_edit_template
  const viewerRole = String(user?.role || '').toLowerCase()
  const contractTypes = (data?.contract_types || fallbackContractTypes).filter((item) => (
    permissions.can_export_bulk || canConfigure || !item.roles || item.roles.includes(viewerRole)
  ))
  const contractLabel = data?.contract_label || fallbackContractTypes.find((item) => item.value === contractType)?.label || 'Hợp đồng'
  const eligibleRoleLabels = (data?.roles || []).map((item) => item.label).join(' và ')

  return <div className="feature-page contract-page">
    <div className="page-heading">
      <div><span className="eyebrow"><FileSignature size={14} /> Hồ sơ lao động</span><h1>HỢP ĐỒNG</h1><p>Chọn loại hợp đồng cần mở và xuất cho một hoặc nhiều nhân viên.</p></div>
      <button className="secondary-button" onClick={() => load(contractType)} disabled={Boolean(busy)}><RefreshCw size={16} className={busy === 'load' ? 'spin' : ''} /> Làm mới</button>
    </div>

    {notice && <div className={notice.type === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}

    <section className="panel contract-type-panel">
      <div className="panel-title-row"><div><h2><FileSignature size={18} /> Chọn loại hợp đồng</h2></div></div>
      <div className="contract-type-list">
        {contractTypes.map((item) => <button
          type="button"
          key={item.value}
          className={`contract-type-button ${contractType === item.value ? 'active' : ''}`.trim()}
          onClick={() => selectContractType(item.value)}
          disabled={Boolean(busy)}
        ><FileSignature size={18} /> {item.label}</button>)}
      </div>
    </section>

    <section className="panel contract-export-panel">
      <div className="panel-title-row"><div><h2><Users size={18} /> Chọn đối tượng xuất {contractLabel}</h2><p>Nếu bất kỳ người lao động nào thiếu thông tin bắt buộc, hệ thống sẽ dừng xuất PDF và thông báo rõ tên cùng nội dung cần bổ sung.</p></div><span className="contract-count">{exportCount} hợp đồng</span></div>
      {permissions.can_export_bulk && <div className="contract-scope-tabs">
        {scopeOptions.map((item) => <button type="button" key={item.value} className={scope === item.value ? 'active' : ''} onClick={() => setScope(item.value)}>{item.label}</button>)}
      </div>}
      {scope === 'selected' && <div className="contract-selected-scope">
        {permissions.can_export_bulk && <label className="contract-search"><Search size={16} /><input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Tìm tên hoặc tài khoản nhân viên…" /></label>}
        <div className="contract-selection-actions">
          <button type="button" className="secondary-button" onClick={selectFiltered} disabled={!filteredEmployees.length}><CheckSquare size={16} /> Chọn tất cả đang hiển thị</button>
          <button type="button" className="secondary-button" onClick={clearSelected} disabled={!selectedUsernames.length}><Square size={16} /> Bỏ chọn</button>
        </div>
        <div className="contract-employee-list">
          {filteredEmployees.map((item) => <label key={item.username} className={selectedSet.has(item.username) ? 'selected' : ''}>
            <input type="checkbox" checked={selectedSet.has(item.username)} onChange={() => toggleEmployee(item.username)} />
            <span><b>{item.full_name}</b><small>{item.username} · {item.role_label}</small></span>
          </label>)}
          {!filteredEmployees.length && <div className="empty-state compact">Không tìm thấy nhân viên phù hợp.</div>}
        </div>
      </div>}
      {scope === 'department' && <label className="contract-department">Bộ phận<select value={role} onChange={(event) => setRole(event.target.value)}>{(data?.roles || []).map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}</select></label>}
      {scope === 'all' && <div className="contract-all-note">File PDF sẽ gồm {contractLabel} của toàn bộ {eligibleRoleLabels || 'nhân viên phù hợp'} đang làm việc, đang hiển thị trong hệ thống.</div>}
      <div className="contract-export-actions">
        <button className="primary-button" onClick={exportContracts} disabled={Boolean(busy) || !canExport || exportCount < 1}><Download size={17} /> {busy === 'export' ? 'Đang kiểm tra và tạo PDF…' : `Xuất ${exportCount || ''} ${contractLabel}`}</button>
        {!canExport && <small>Tài khoản chưa được cấp quyền xuất hợp đồng tương ứng.</small>}
      </div>
    </section>

    {canConfigure && settings && <section className="panel contract-settings-panel">
      <div className="panel-title-row"><div><h2><Settings2 size={18} /> Cài đặt {contractLabel}</h2><p>Thay đổi thông tin người đại diện, thời hạn, ngày ký, mức lương và nội dung mẫu riêng của loại hợp đồng này.</p></div></div>
      <div className="contract-settings-grid">
        {settingFields.map(([key, label]) => <label key={key} className={`${key === 'business_address' ? 'span-2' : ''} ${['contract_term', 'signing_date'].includes(key) ? 'contract-highlight-field' : ''}`.trim()}>{label}{key === 'signing_date' ? <VeraDateInput aria-label={label} value={settings[key] || ''} disabled={!permissions.can_edit_settings} onChange={(event) => setSettings({ ...settings, [key]: event.target.value })} /> : <input type="text" value={settings[key] || ''} disabled={!permissions.can_edit_settings} onChange={(event) => setSettings({ ...settings, [key]: event.target.value })} />}</label>)}
      </div>
      <label className="contract-template-field">Nội dung mẫu hợp đồng<textarea rows="20" value={settings.template_content || ''} disabled={!permissions.can_edit_template} onChange={(event) => setSettings({ ...settings, template_content: event.target.value })} /></label>
      <details className="contract-placeholders"><summary>Biến tự động có thể dùng trong mẫu</summary><div>{placeholderHelp.map((item) => <code key={item}>{item}</code>)}</div></details>
      <div className="contract-save-actions"><button className="primary-button" onClick={save} disabled={Boolean(busy)}><Save size={17} /> {busy === 'save' ? 'Đang lưu…' : 'Lưu cài đặt hợp đồng'}</button></div>
    </section>}
  </div>
}
