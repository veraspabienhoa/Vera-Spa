import { searchTextMatches } from '../lib/searchText'
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
  const featureAllowed = (key, role, account = '', source = data) => {
    const accountOverride = source?.account_overrides?.[account] || {}
    const roleOverride = source?.role_overrides?.[role] || {}
    if (Object.hasOwn(accountOverride, key)) return accountOverride[key]
    if (Object.hasOwn(roleOverride, key)) return roleOverride[key]
    const legacy = source?.legacy_inheritance?.[key]
    return legacy ? featureAllowed(legacy, role, account, source) : (source?.defaults?.[role] || []).includes(key)
  }
  const roleAllowed = (role, source = data) => {
    return allFeatureKeys(source).filter((key) => featureAllowed(key, role, '', source))
  }
  const expandDependencies = (features, source = data) => {
    const dependencies = source?.dependencies || {}
    const expanded = new Set(features)
    let changed = true
    while (changed) {
      changed = false
      for (const feature of [...expanded]) {
        for (const required of dependencies[feature] || []) {
          if (!expanded.has(required)) {
            expanded.add(required)
            changed = true
          }
        }
      }
    }
    return [...expanded]
  }
  const dependentFeatures = (feature, source = data) => {
    const all = allFeatureKeys(source)
    return all.filter((candidate) => candidate !== feature && expandDependencies([candidate], source).includes(feature))
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
        : allFeatureKeys(source).filter((key) => featureAllowed(key, account?.role, nextTarget, source)))
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
    setAllowed((current) => {
      if (!current.includes(feature)) return expandDependencies([...current, feature])
      const blocked = new Set([feature, ...dependentFeatures(feature)])
      return current.filter((item) => !blocked.has(item))
    })
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
      const normalizedAllowed = inherit ? allowed : expandDependencies(allowed)
      const result = await veraApi.savePermissions(scope, target, { allowed_features: normalizedAllowed, inherit, expected_revision: data.revision })
      const refreshed = await load({ keepNotice: true })
      if (refreshed) applyTarget(scope, target, refreshed)
      setNotice({ status: 'success', message: result.message })
    } catch (error) {
      setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message})` })
      setBusy(false)
    }
  }
  const groups = useMemo(() => Object.entries(data?.groups || {}).map(([label, items]) => [label, Object.entries(items).filter(([key, value]) => searchTextMatches([key, value], search))]).filter(([, items]) => items.length), [data, search])

  return <div className="feature-page permissions-page">
    <style>{`
      .permission-account-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
      .permission-account-actions small{color:#65736d}
      .permission-account-state{font-weight:900;color:#1f513f}
      .permission-dependency-note{margin:8px 0 0;padding:9px 11px;border-radius:9px;background:#eef7f2;color:#315345;font-size:11px;line-height:1.45}
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
      <p className="permission-dependency-note">Quyền phụ thuộc được tự động đồng bộ: khi bật một quyền thao tác, hệ thống tự bật các quyền Xem / khu vực nền cần thiết; khi tắt quyền nền, các quyền thao tác phụ thuộc cũng tự tắt. Quy tắc này áp dụng cho cả phân quyền theo nhóm và theo tài khoản.</p>
    </section>
    <div className="permission-groups">
      {groups.map(([label, items]) => <section className="panel permission-group" key={label}><div className="permission-group-head"><h2>{label}</h2><span>{items.filter(([key]) => allowed.includes(key)).length}/{items.length}</span></div><div className="permission-check-grid">{items.map(([key, value]) => <label key={key} className={allowed.includes(key) ? 'checked' : ''}><input type="checkbox" checked={allowed.includes(key)} onChange={() => toggle(key)} /><span><strong>{value}</strong><small>{key}</small></span></label>)}</div></section>)}
    </div>
    <div className="sticky-save-bar"><button className="primary-button" onClick={save} disabled={busy || !target}><Save size={16} /> {busy ? 'Đang lưu…' : 'Lưu phân quyền'}</button></div>
  </div>
}
