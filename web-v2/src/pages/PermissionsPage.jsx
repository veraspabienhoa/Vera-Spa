import { RefreshCw, Save, Search, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'

const roleLabel = { giamdoc: 'Giám đốc', quanly: 'Quản lý', letan: 'Lễ tân', leader: 'Leader', nhanvien: 'Nhân viên', locker: 'Locker', tapvu: 'Tạp vụ' }

export default function PermissionsPage() {
  const [data, setData] = useState(null)
  const [scope, setScope] = useState('role')
  const [target, setTarget] = useState('quanly')
  const [allowed, setAllowed] = useState([])
  const [inherit, setInherit] = useState(false)
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)

  const allFeatureKeys = (source = data) => Object.values(source?.groups || {}).flatMap((items) => Object.keys(items))
  const roleAllowed = (role, source = data) => {
    const override = source?.role_overrides?.[role] || {}
    const defaults = source?.defaults?.[role] || []
    return allFeatureKeys(source).filter((key) => Object.prototype.hasOwnProperty.call(override, key) ? override[key] : defaults.includes(key))
  }
  const applyTarget = (nextScope, nextTarget, source = data) => {
    if (!source) return
    if (nextScope === 'role') {
      setAllowed(roleAllowed(nextTarget, source))
      setInherit(false)
    } else {
      const override = source.account_overrides?.[nextTarget] || {}
      const account = source.accounts.find((item) => item.username === nextTarget)
      const isInherited = Object.keys(override).length === 0
      setInherit(isInherited)
      const roleFeatures = roleAllowed(account?.role, source)
      setAllowed(isInherited
        ? roleFeatures
        : allFeatureKeys(source).filter((key) => Object.prototype.hasOwnProperty.call(override, key) ? override[key] : roleFeatures.includes(key)))
    }
  }
  const load = async ({ keepNotice = false } = {}) => {
    setBusy(true)
    if (!keepNotice) setNotice(null)
    try {
      const result = await veraApi.permissions()
      setData(result)
      applyTarget(scope, target, result)
      return result
    } catch (error) {
      setNotice({ status: 'error', message: error.message })
      return null
    } finally {
      setBusy(false)
    }
  }
  useEffect(() => { void load() }, []) // eslint-disable-line react-hooks/exhaustive-deps
  const chooseScope = (value) => {
    const nextTarget = value === 'role' ? 'quanly' : (data?.accounts?.[0]?.username || '')
    setScope(value); setTarget(nextTarget); applyTarget(value, nextTarget)
  }
  const chooseTarget = (value) => { setTarget(value); applyTarget(scope, value) }
  const toggle = (feature) => {
    // Clicking any permission while the account is inheriting automatically
    // starts a private override from the inherited role baseline.
    if (scope === 'account' && inherit) setInherit(false)
    setAllowed((current) => current.includes(feature) ? current.filter((item) => item !== feature) : [...current, feature])
  }
  const enablePrivatePermissions = () => {
    if (scope !== 'account') return
    const account = data?.accounts?.find((item) => item.username === target)
    if (!allowed.length) setAllowed(roleAllowed(account?.role))
    setInherit(false)
  }
  const resetToRolePermissions = () => {
    if (scope !== 'account') return
    const account = data?.accounts?.find((item) => item.username === target)
    setAllowed(roleAllowed(account?.role))
    setInherit(true)
  }
  const save = async () => {
    setBusy(true); setNotice(null)
    try {
      const result = await veraApi.savePermissions(scope, target, { allowed_features: allowed, inherit, expected_revision: data.revision })
      await load({ keepNotice: true })
      setNotice({ status: 'success', message: result.message })
    } catch (error) {
      setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message})` })
      setBusy(false)
    }
  }
  const groups = useMemo(() => Object.entries(data?.groups || {}).map(([label, items]) => [label, Object.entries(items).filter(([key, value]) => `${key} ${value}`.toLowerCase().includes(search.toLowerCase()))]).filter(([, items]) => items.length), [data, search])

  return <div className="feature-page permissions-page">
    <style>{`
      .permission-account-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
      .permission-account-actions small{color:#65736d}
      .permission-account-state{font-weight:900;color:#1f513f}
    `}</style>
    <div className="page-heading"><div><span className="eyebrow"><ShieldCheck size={14} /> Admin</span><h1>PHÂN QUYỀN</h1><p>Phân quyền chi tiết theo nhóm hoặc ghi đè riêng cho từng tài khoản.</p></div><button className="secondary-button" onClick={() => load()} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /> Làm mới</button></div>
    {notice && <div className={notice.status === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}
    <section className="panel permission-target-panel">
      <div className="permission-scope-tabs"><button className={scope === 'role' ? 'active' : ''} onClick={() => chooseScope('role')}>Theo nhóm</button><button className={scope === 'account' ? 'active' : ''} onClick={() => chooseScope('account')}>Theo tài khoản</button></div>
      <label>{scope === 'role' ? 'Chọn nhóm' : 'Chọn tài khoản'}<select value={target} onChange={(e) => chooseTarget(e.target.value)}>{scope === 'role' ? data?.roles?.map((role) => <option key={role} value={role}>{roleLabel[role] || role}</option>) : data?.accounts?.map((item) => <option key={item.username} value={item.username}>{item.username} · {roleLabel[item.role] || item.role}</option>)}</select></label>
      {scope === 'account' && <>
        <label className="inherit-toggle"><input type="checkbox" checked={inherit} onChange={(e) => e.target.checked ? resetToRolePermissions() : enablePrivatePermissions()} /> Kế thừa quyền của nhóm</label>
        <div className="permission-account-actions">
          {inherit
            ? <button type="button" className="secondary-button" onClick={enablePrivatePermissions}>Phân quyền riêng tài khoản này</button>
            : <button type="button" className="secondary-button" onClick={resetToRolePermissions}>Dùng lại quyền của nhóm</button>}
          <small>Trạng thái: <span className="permission-account-state">{inherit ? 'Đang kế thừa theo nhóm' : 'Đang phân quyền riêng'}</span>. Có thể bấm trực tiếp vào bất kỳ quyền nào để tạo ghi đè riêng.</small>
        </div>
      </>}
      <label className="permission-search"><Search size={16} /><input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm quyền…" /></label>
    </section>
    <div className="permission-groups">
      {groups.map(([label, items]) => <section className="panel permission-group" key={label}><div className="permission-group-head"><h2>{label}</h2><span>{items.filter(([key]) => allowed.includes(key)).length}/{items.length}</span></div><div className="permission-check-grid">{items.map(([key, value]) => <label key={key} className={allowed.includes(key) ? 'checked' : ''}><input type="checkbox" checked={allowed.includes(key)} onChange={() => toggle(key)} /><span><strong>{value}</strong><small>{key}</small></span></label>)}</div></section>)}
    </div>
    <div className="sticky-save-bar"><button className="primary-button" onClick={save} disabled={busy || !target}><Save size={16} /> {busy ? 'Đang lưu…' : 'Lưu phân quyền'}</button></div>
  </div>
}