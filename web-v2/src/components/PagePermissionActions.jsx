import { createContext, useContext, useEffect, useState } from 'react'
import { veraApi } from '../lib/api'
import { catalogAllowedFeatures, catalogFeatureAllowed, canEditCatalogFeature, hasAnyDateParent, supportsDateFilterPolicy, datePermissionSaveProblem } from '../lib/permissionCatalog'
import { searchTextMatches } from '../lib/searchText'
import EmployeeProfileModal from './EmployeeProfileModal'
import './PagePermissionActions.css'

const UserContext = createContext(null)
export function PagePermissionProvider({ user, children }) { return <UserContext.Provider value={user}>{children}</UserContext.Provider> }
const aliases = {
  system: ['changes', 'storage'], settings: ['live-tour-settings', 'ktv-shift', 'schedule', 'permissions'],
  'department-payroll': ['payroll'], 'payroll-config': ['payroll'], 'checkin-history': ['devices'],
  'hc-rules': ['rules'], purchases: ['other:Nhập mua'],
}
const fixedPages = { hr: 'Nhân sự chỉ dành cho Admin', notifications: 'Cấu hình thông báo chỉ dành cho Admin', 'payroll-config': 'Cấu hình lương chỉ dành cho Admin', 'hc-rules': 'Nội quy hành chánh chỉ dành cho Admin', 'online-bookings': 'Booking online giới hạn theo vai trò Admin, Quản lý, Lễ tân và Locker', 'milk-tea': 'Trà sữa giới hạn theo vai trò Leader và Nhân viên' }

function scopedPermissionPages(data, page, features) {
  const ids = aliases[page] || [page]
  return (data?.pages || []).map(item => ({ ...item, features: Object.fromEntries(Object.entries(item.features || {}).filter(([key]) => canEditCatalogFeature(key, data) && (features ? features.includes(key) : ids.includes(item.id)))) })).filter(item => Object.keys(item.features).length)
}
function toggleScopedPermission(current, key, data) {
  const expand = (keys) => {
    const result = new Set(keys), pending = [...keys]
    while (pending.length) {
      const item = pending.pop()
      for (const parent of data.dependencies?.[item] || []) if (!result.has(parent)) { result.add(parent); if (!Object.hasOwn(data.date_filter_features || {}, item)) pending.push(parent) }
    }
    return result
  }
  if (!current.includes(key)) return [...new Set([...current, ...expand([key])])]
  const next = current.filter(item => item !== key && !expand([item]).has(key))
  return next.filter(item => hasAnyDateParent(item, next, data))
}

export default function PagePermissionActions({ page, label, features, viewFeatures, adminOnly = false }) {
  const user = useContext(UserContext)
  const [mode, setMode] = useState('')
  if (user?.role !== 'admin' || user?.must_change_password) return null
  return <div className="page-permission-actions">
    <button type="button" className="secondary-button" onClick={() => setMode('edit')}>Phân quyền{label ? ` · ${label}` : ''}</button>
    <button type="button" className="secondary-button" onClick={() => setMode('list')}>Tài khoản đã được phân quyền{label ? ` · ${label}` : ''}</button>
    {mode && <PermissionDialog key={`${page}:${label || ''}:${mode}`} {...{page, label, features, viewFeatures, adminOnly, mode}} onClose={() => setMode('')}/>}
  </div>
}
function PermissionDialog({ page, label, features, viewFeatures, adminOnly, mode, onClose }) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [query, setQuery] = useState(''), [target, setTarget] = useState(''), [allowed, setAllowed] = useState([])
  useEffect(() => { let active = true; setBusy(true); veraApi.permissions().then(result => { if (active) setData(result) }).catch(err => { if (active) setError(err.message) }).finally(() => { if (active) setBusy(false) }); return () => { active = false } }, [])
  const pages = scopedPermissionPages(data, page, features)
  const keys = pages.flatMap(item => Object.keys(item.features))
  const required = viewFeatures || pages.flatMap(item => item.view_feature && Object.hasOwn(item.features, item.view_feature) ? [item.view_feature] : Object.keys(item.features))
  const fixed = adminOnly ? 'Tab này chỉ dành cho Admin theo quy tắc máy chủ.' : fixedPages[page]
  const accounts = (data?.accounts || []).filter(account => searchTextMatches([account.username, account.full_name, account.role], query))
  const canView = account => fixed ? (adminOnly || !['online-bookings', 'milk-tea'].includes(page) ? account.role === 'admin' : (page === 'online-bookings' ? ['admin', 'quanly', 'letan', 'locker'] : ['leader', 'nhanvien']).includes(account.role)) : required.some(key => catalogFeatureAllowed(key, account.role, account.username, data))
  const choose = account => { setTarget(account.username); setAllowed(catalogAllowedFeatures(account.role, account.username, data)); setError(''); setNotice('') }
  const account = data?.accounts?.find(item => item.username === target)
  const save = async () => {
    setBusy(true); setError(''); setNotice('')
    try {
      if (data.scoped_permission_policy_version !== 1) throw new Error('Máy chủ cần được cập nhật để lưu quyền theo trang. Hãy tải lại sau khi triển khai.')
      const baseline = catalogAllowedFeatures(account.role, target, data)
      const edited = [...new Set([...baseline, ...allowed])].filter(key => baseline.includes(key) !== allowed.includes(key))
      if (!edited.length) { setNotice('Không có thay đổi phân quyền.'); return }
      const result = await veraApi.savePermissions('account', target, {allowed_features: allowed, edited_features: edited, inherit: false, expected_revision: data.revision, preserve_unchanged: true, ...(supportsDateFilterPolicy(data) ? {date_filter_policy_version: 1} : {})})
      const refreshed = await veraApi.permissions()
      const problem = supportsDateFilterPolicy(data) ? datePermissionSaveProblem(result, refreshed) : ''
      setData(refreshed)
      setAllowed(catalogAllowedFeatures(account.role, target, refreshed))
      if (problem) throw new Error(problem)
      if (result.scoped_permission_policy_version !== 1 || refreshed.scoped_permission_policy_version !== 1) throw new Error('Chưa xác minh được quyền vừa lưu. Hãy tải lại phân quyền.')
      setNotice('Đã lưu phân quyền tài khoản.')
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <EmployeeProfileModal labelledBy="page-permission-title" busy={busy} onClose={onClose} className="page-permission-modal"><section>
    <header><h2 id="page-permission-title">{mode === 'list' ? 'Tài khoản đã được phân quyền' : 'Phân quyền'} · {label || pages.map(item => item.label).join(' / ') || page}</h2><button type="button" disabled={busy} onClick={onClose}>Đóng</button></header>
    {fixed && <p>{fixed}. Các quyền khác không thay đổi giới hạn này.</p>}
    <p>Các tab dùng chung quyền sẽ cùng chịu tác động khi thay đổi quyền đó.</p>
    <label>Tìm tài khoản<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Tên tài khoản, họ tên hoặc nhóm"/></label>
    {busy && <p role="status">Đang xử lý…</p>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="permission-account-results">{accounts.filter(item => mode !== 'list' || canView(item)).map(item => <button type="button" key={item.username} disabled={busy || mode === 'list'} aria-pressed={target === item.username} onClick={() => choose(item)}><strong>{item.username}</strong> · {item.full_name} · {item.role}<small>{item.role === 'admin' ? 'Admin' : Object.keys(data.account_overrides?.[item.username] || {}).length ? 'Quyền riêng tài khoản' : 'Kế thừa nhóm'}</small></button>)}</div>
    {data && !accounts.filter(item => mode !== 'list' || canView(item)).length && <p>Không có tài khoản phù hợp.</p>}
    {mode === 'edit' && account && <fieldset disabled={busy || account.role === 'admin' || Boolean(fixed)}><legend>Quyền của {target}</legend>{pages.map(item => <div key={item.id}><h3>{item.label}</h3>{Object.entries(item.features).map(([key, text]) => <label className="context-permission-check" key={key}><input type="checkbox" checked={allowed.includes(key)} disabled={!hasAnyDateParent(key, allowed, data)} onChange={() => setAllowed(current => toggleScopedPermission(current, key, data))}/>{text}</label>)}</div>)}{keys.length > 0 && <button type="button" className="primary-button" onClick={save}>Lưu phân quyền</button>}</fieldset>}
    {data && !keys.length && !fixed && <p>Trang này chưa có quyền riêng trong danh mục máy chủ.</p>}
  </section></EmployeeProfileModal>
}
