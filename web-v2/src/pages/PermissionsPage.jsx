import usePageRefresh from '../lib/usePageRefresh'
import StableFeedback from '../components/StableFeedback'
import UiToolbar from '../components/UiToolbar'
import UiCustomText from '../components/UiCustomText'
import { searchTextMatches } from '../lib/searchText'
import { RefreshCw, Save, ShieldCheck } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { veraApi } from '../lib/api'
import { canEditCatalogFeature, catalogAllowedFeatures, datePermissionSaveProblem, hasAnyDateParent, permissionFeatureKeys, supportsDateFilterPolicy } from '../lib/permissionCatalog'

const roleLabel = { giamdoc: 'Giám đốc', quanly: 'Quản lý', letan: 'Lễ tân', leader: 'Leader', nhanvien: 'Nhân viên', locker: 'Locker', tapvu: 'Tạp vụ' }

export default function PermissionsPage() {
  usePageRefresh(() => load(), () => Boolean(busy || refreshDirty))
  const [data, setData] = useState(null)
  const [scope, setScope] = useState('role')
  const [target, setTarget] = useState('quanly')
  const [allowed, setAllowed] = useState([])
  const [inherit, setInherit] = useState(false)
  const [search, setSearch] = useState('')
  const [busy, setBusy] = useState(false)
  const [notice, setNotice] = useState(null)
  const [refreshDirty, setRefreshDirty] = useState(false)

  const allFeatureKeys = (source = data) => permissionFeatureKeys(source)
  const roleAllowed = (role, source = data) => catalogAllowedFeatures(role, '', source)
  const expandDependencies = (features, source = data) => {
    const dependencies = source?.dependencies || {}
    const expanded = new Set(features)
    const pending = [...features]
    const visited = new Set()
    while (pending.length) {
      const feature = pending.pop()
      if (visited.has(feature)) continue
      visited.add(feature)
      for (const required of dependencies[feature] || []) {
        expanded.add(required)
        if (!Object.hasOwn(source?.date_filter_features || {}, feature)) pending.push(required)
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
    setRefreshDirty(false)
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
        : catalogAllowedFeatures(account?.role, nextTarget, source))
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
    setRefreshDirty(true)
    // Clicking any permission while the account is inheriting automatically
    // starts a private override from the inherited role baseline.
    if (scope === 'account' && inherit) setInherit(false)
    setAllowed((current) => {
      if (!current.includes(feature)) return [...new Set([...current, ...expandDependencies([feature])])]
      const blocked = new Set([feature, ...dependentFeatures(feature)])
      const remaining = current.filter((item) => !blocked.has(item))
      return remaining.filter((item) => hasAnyDateParent(item, remaining, data))
    })
  }
  const enablePrivatePermissions = () => {
    setRefreshDirty(true)
    if (scope !== 'account') return
    const account = data?.accounts?.find((item) => item.username === target)
    if (!allowed.length) setAllowed(roleAllowed(account?.role))
    setInherit(false)
  }
  const resetToRolePermissions = () => {
    setRefreshDirty(true)
    if (scope !== 'account') return
    const account = data?.accounts?.find((item) => item.username === target)
    setAllowed(roleAllowed(account?.role))
    setInherit(true)
  }
  const save = async () => {
    setBusy(true); setNotice(null)
    try {
      // Toggles expand newly chosen actions. An unchanged save must not expand
      // inherited legacy actions over an existing explicit view denial.
      const normalizedAllowed = allowed
      const editsDatePolicy = supportsDateFilterPolicy(data)
      const result = await veraApi.savePermissions(scope, target, { allowed_features: normalizedAllowed, inherit, expected_revision: data.revision, preserve_unchanged: true, ...(editsDatePolicy ? { date_filter_policy_version: 1 } : {}) })
      const refreshed = await load({ keepNotice: true })
      if (refreshed) applyTarget(scope, target, refreshed)
      const verificationProblem = editsDatePolicy ? datePermissionSaveProblem(result, refreshed) : ''
      if (verificationProblem) {
        setNotice({ status: 'error', message: verificationProblem })
        return
      }
      setNotice({ status: 'success', message: result.message })
    } catch (error) {
      setNotice({ status: 'error', message: `KHÔNG THÀNH CÔNG (${error.message})` })
      setBusy(false)
    }
  }
  const pages = useMemo(() => (data?.pages || []).map((page) => {
    const items = Object.entries(page?.features || {}).filter(([key, value]) => canEditCatalogFeature(key, data) && searchTextMatches([page.label, key, value], search))
    return { ...page, items }
  }).filter((page) => page.items.length), [data, search])

  return <div className="feature-page permissions-page">
    <style>{`
      .permission-account-actions{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-top:8px}
      .permission-account-actions small{color:#65736d}
      .permission-account-state{font-weight:900;color:#1f513f}
      .permission-pages{display:grid;gap:14px}
      .permission-page-card{border:1px solid #dce7e1;border-radius:15px;overflow:hidden;background:#fff}
      .permission-page-head{display:flex;align-items:center;justify-content:space-between;gap:12px;padding:12px 14px;background:#f4f8f6;border-bottom:1px solid #e4ece8}
      .permission-page-head h2{margin:0;font-size:16px;color:#173329}
      .permission-page-head span{font-size:11px;font-weight:900;color:#52675e}
      .permission-page-actions{padding:12px 14px}
      .permission-view-permission{border-color:#9fc8b6!important;background:#eef8f3!important}
      .permission-view-permission strong:after{content:' · MỞ TRANG';font-size:9px;color:#2d6a50;font-weight:900}
    `}</style>
    <div data-ui-key="u-7f40edd7308c" className="page-heading"><div><span className="eyebrow"><ShieldCheck size={14} /> Admin</span><h1>PHÂN QUYỀN THEO TRANG</h1><p>Mỗi trang/menu có các tác vụ riêng. Admin có thể cấp từng tác vụ cho nhóm hoặc cho từng tài khoản.</p></div><button data-ui-key="u-9d2013a3b024" data-ui-label-default="Làm mới" className="secondary-button" onClick={() => load()} disabled={busy}><RefreshCw size={16} className={busy ? 'spin' : ''} /><UiCustomText uiKey="u-9d2013a3b024"> Làm mới</UiCustomText></button></div>
    <StableFeedback>{notice && <div className={notice.status === 'success' ? 'success-box' : 'error-box'}>{notice.message}</div>}</StableFeedback>
    <section data-ui-key="u-651db1ae818d" className="panel permission-target-panel">
      <UiToolbar data-ui-key="u-a0020edbc857" className="permission-scope-tabs"><button data-ui-key="u-f183ddd5f06a" data-ui-label-default="Theo nhóm" className={scope === 'role' ? 'active' : ''} onClick={() => chooseScope('role')}><UiCustomText uiKey="u-f183ddd5f06a">Theo nhóm</UiCustomText></button><button data-ui-key="u-cd99f6cb1fbe" data-ui-label-default="Theo tài khoản" className={scope === 'account' ? 'active' : ''} onClick={() => chooseScope('account')}><UiCustomText uiKey="u-cd99f6cb1fbe">Theo tài khoản</UiCustomText></button></UiToolbar>
      <label>{scope === 'role' ? 'Chọn nhóm' : 'Chọn tài khoản'}<select value={target} onChange={(e) => chooseTarget(e.target.value)}>{scope === 'role' ? data?.roles?.map((role) => <option key={role} value={role}>{roleLabel[role] || role}</option>) : data?.accounts?.map((item) => <option key={item.username} value={item.username}>{item.username} · {roleLabel[item.role] || item.role}</option>)}</select></label>
      {scope === 'account' && <>
        <label className="inherit-toggle"><input type="checkbox" checked={inherit} onChange={(e) => e.target.checked ? resetToRolePermissions() : enablePrivatePermissions()} /> Kế thừa quyền của nhóm</label>
        <UiToolbar data-ui-key="u-ee7b6fa542d8" className="permission-account-actions">
          {inherit
            ? <button data-ui-key="u-8fac46410269" data-ui-label-default="Phân quyền riêng tài khoản này" type="button" className="secondary-button" onClick={enablePrivatePermissions}><UiCustomText uiKey="u-8fac46410269">Phân quyền riêng tài khoản này</UiCustomText></button>
            : <button data-ui-key="u-16144bb9f395" data-ui-label-default="Dùng lại quyền của nhóm" type="button" className="secondary-button" onClick={resetToRolePermissions}><UiCustomText uiKey="u-16144bb9f395">Dùng lại quyền của nhóm</UiCustomText></button>}
          <small>Trạng thái: <span className="permission-account-state">{inherit ? 'Đang kế thừa theo nhóm' : 'Đang phân quyền riêng'}</span>. Có thể bấm trực tiếp vào bất kỳ quyền nào để tạo ghi đè riêng.</small>
        </UiToolbar>
      </>}
      <label className="permission-search"><input aria-label="Tìm quyền" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Tìm quyền…" /></label>
      {supportsDateFilterPolicy(data) && <p className="permission-date-note">Mỗi mục Live Tour có 8 quyền lọc ngày riêng. Quyền chưa cấu hình kế thừa quyền xem mục đó; bỏ chọn cả 8 sẽ chặn dữ liệu theo ngày. Lịch sử cần quyền Xem lịch sử hoặc Sao lưu; quyền Sao lưu không mở nội dung nhật ký.</p>}
    </section>
    <div className="permission-pages">
      {pages.map((page) => <section data-ui-key="u-3507366ab96e" className="permission-page-card" key={page.id}>
        <div className="permission-page-head"><h2>{page.label}</h2><span>{page.items.filter(([key]) => allowed.includes(key)).length}/{page.items.length} quyền</span></div>
        <UiToolbar data-ui-key="u-96946da0cd4c" className="permission-check-grid permission-page-actions">
          {page.items.map(([key, value]) => <label key={key} className={`${allowed.includes(key) ? 'checked' : ''} ${page.view_feature === key ? 'permission-view-permission' : ''}`.trim()}><input type="checkbox" checked={allowed.includes(key)} disabled={!hasAnyDateParent(key, allowed, data)} onChange={() => toggle(key)} /><span><strong>{value}</strong><small>{key}</small>{!hasAnyDateParent(key, allowed, data) && <small>Cần Xem lịch sử hoặc Sao lưu</small>}</span></label>)}
        </UiToolbar>
      </section>)}
    </div>
    <div className="sticky-save-bar"><button data-ui-key="u-0ec9baa2f9fd" className="primary-button" onClick={save} disabled={busy || !target}><Save size={16} /> {busy ? 'Đang lưu…' : 'Lưu phân quyền'}</button></div>
  </div>
}
