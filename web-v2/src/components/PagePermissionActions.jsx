import { createContext, useCallback, useContext, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import { alertDialog } from '../lib/systemDialogs'
import { catalogAllowedFeatures, catalogFeatureAllowed, canEditCatalogFeature, hasAnyDateParent, supportsDateFilterPolicy, datePermissionSaveProblem } from '../lib/permissionCatalog'
import { searchTextMatches } from '../lib/searchText'
import EmployeeProfileModal from './EmployeeProfileModal'
import './PagePermissionActions.css'

const UserContext = createContext(null)
const ScopeContext = createContext(null)
export function PagePermissionProvider({ user, page, children }) {
  const [scopes, setScopes] = useState({})
  const register = useCallback((id, value) => {
    setScopes(current => { const next = { ...current }; if (value) next[id] = value; else delete next[id]; return next })
  }, [])
  return <UserContext.Provider value={user}><ScopeContext.Provider value={{ page, scopes, register }}>{children}</ScopeContext.Provider></UserContext.Provider>
}
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

export default function PagePermissionActions({ primary = false, ...scope }) {
  const user = useContext(UserContext), registry = useContext(ScopeContext)
  const id = useId(), marker = useRef(null)
  const serialized = JSON.stringify(scope)
  const register = registry?.register
  const managed = registry?.page !== undefined
  useEffect(() => {
    if (!managed || primary || !register || registry.page === 'live-tour') return undefined
    register(id, { ...JSON.parse(serialized), element: marker.current })
    return () => register(id, null)
  }, [managed, primary, register, registry?.page, id, serialized])
  if (user?.role !== 'admin' || user?.must_change_password || scope.page === 'live-tour' || registry?.page === 'live-tour') return null
  if (managed && !primary) return <span ref={marker} hidden data-permission-scope=""/>
  return <PermissionLauncher key={`${registry?.page || scope.page}:${user.employee_username || ''}`} scope={scope} scopes={managed ? Object.values(registry.scopes) : []} attachToTitle={primary}/>
}
function PermissionLauncher({ scope, scopes, attachToTitle }) {
  const [menu, setMenu] = useState(false), [selection, setSelection] = useState(null), [heading, setHeading] = useState(null)
  const anchor = useRef(null)
  useLayoutEffect(() => {
    if (!attachToTitle) return undefined
    const container = anchor.current?.parentElement
    if (!container) return undefined
    const host = document.createElement('span')
    host.className = 'permission-title-action'
    let title = null
    const findHeading = () => {
      const visible = node => !node.closest('[hidden], [role="dialog"], .page-recovery, [role="alert"], .page-loading')
      const next = [...container.querySelectorAll('h1')].find(visible) || [...container.querySelectorAll('h2')].find(visible) || null
      if (title !== next) { title?.classList.remove('permission-title-row'); title = next }
      if (title) {
        title.classList.add('permission-title-row')
        if (host.parentElement !== title) title.appendChild(host)
      } else host.remove()
      setHeading(current => current === (title ? host : null) ? current : title ? host : null)
    }
    findHeading()
    const observer = new MutationObserver(findHeading)
    observer.observe(container, { childList: true, subtree: true, attributes: true, attributeFilter: ['hidden'] })
    return () => { observer.disconnect(); title?.classList.remove('permission-title-row'); host.remove() }
  }, [attachToTitle])
  const options = [scope, ...scopes.filter(item => item.element?.isConnected && !item.element.parentElement?.closest('[hidden]'))]
    .filter((item, index, all) => all.findIndex(other => other.page === item.page && other.label === item.label) === index)
  const launcher = <button type="button" className="secondary-button page-permission-launcher" aria-haspopup="dialog" onClick={() => setMenu(true)}>Phân quyền</button>
  return <>
    <span ref={anchor} hidden/>
    {attachToTitle ? heading && createPortal(launcher, heading) : launcher}
    {menu && !selection && <EmployeeProfileModal labelledBy="permission-menu-title" onClose={() => setMenu(false)} className="page-permission-modal">
      <header><h2 id="permission-menu-title">Phân quyền</h2><button type="button" onClick={() => setMenu(false)}>Đóng</button></header>
      <div className="permission-menu-options">{options.map(item => <section key={`${item.page}:${item.label || ''}`}>
        <h3>{item.label || 'Trang hiện tại'}</h3>
        <button type="button" className="secondary-button" onClick={() => setSelection({ scope: item, mode: 'edit' })}>Phân quyền{item.label ? ` · ${item.label}` : ' trang'}</button>
        <button type="button" className="secondary-button" onClick={() => setSelection({ scope: item, mode: 'list' })}>Tài khoản đã được phân quyền{item.label ? ` · ${item.label}` : ''}</button>
      </section>)}</div>
    </EmployeeProfileModal>}
    {selection && <PermissionDialog {...selection.scope} mode={selection.mode} onClose={() => setSelection(null)}/>}
  </>
}
function PermissionDialog({ page, label, features, viewFeatures, adminOnly, mode, onClose }) {
  const [data, setData] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [query, setQuery] = useState(''), [target, setTarget] = useState(''), [allowed, setAllowed] = useState([])
  useEffect(() => { let active = true; setBusy(true); veraApi.permissions().then(result => { if (active) setData(result) }).catch(err => { if (active) setError(err.message) }).finally(() => { if (active) setBusy(false) }); return () => { active = false } }, [])
  const pages = scopedPermissionPages(data, page, features)
  const keys = pages.flatMap(item => Object.keys(item.features))
  const required = viewFeatures || pages.flatMap(item => item.view_feature && Object.hasOwn(item.features, item.view_feature) ? [item.view_feature] : Object.keys(item.features))
  const missingView = viewFeatures?.some(key => !(data?.pages || []).some(item => Object.hasOwn(item.features || {}, key)))
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
      await alertDialog('Đã lưu thành công.', { kind: 'success', title: 'Lưu phân quyền' })
    } catch (err) { setError(err.message) } finally { setBusy(false) }
  }
  return <EmployeeProfileModal labelledBy="page-permission-title" busy={busy} onClose={onClose} className="page-permission-modal"><section>
    <header><h2 id="page-permission-title">{mode === 'list' ? 'Tài khoản đã được phân quyền' : 'Phân quyền'} · {label || pages.map(item => item.label).join(' / ') || page}</h2><button type="button" disabled={busy} onClick={onClose}>Đóng</button></header>
    {data && missingView && <p role="alert">Máy chủ chưa có quyền riêng cho tab này. Cần cập nhật máy chủ rồi tải lại phân quyền.</p>}
    {fixed && <p>{fixed}. Các quyền khác không thay đổi giới hạn này.</p>}
    <p>Các tab dùng chung quyền sẽ cùng chịu tác động khi thay đổi quyền đó.</p>
    <label>Tìm tài khoản<input type="search" value={query} onChange={event => setQuery(event.target.value)} placeholder="Tên tài khoản, họ tên hoặc nhóm"/></label>
    {busy && <p role="status">Đang xử lý…</p>}{error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <div className="permission-account-results">{accounts.filter(item => mode !== 'list' || canView(item)).map(item => <button type="button" key={item.username} disabled={busy || mode === 'list'} aria-pressed={target === item.username} onClick={() => choose(item)}><strong>{item.username}</strong> · {item.full_name} · {item.role}<small>{item.role === 'admin' ? 'Admin' : Object.keys(data.account_overrides?.[item.username] || {}).length ? 'Quyền riêng tài khoản' : 'Kế thừa nhóm'}</small></button>)}</div>
    {data && !accounts.filter(item => mode !== 'list' || canView(item)).length && <p>Không có tài khoản phù hợp.</p>}
    {mode === 'edit' && account && <fieldset disabled={busy || account.role === 'admin' || Boolean(fixed) || Boolean(missingView)}><legend>Quyền của {target}</legend>{pages.map(item => <div key={item.id}><h3>{item.label}</h3>{Object.entries(item.features).map(([key, text]) => <label className="context-permission-check" key={key}><input type="checkbox" checked={allowed.includes(key)} disabled={!hasAnyDateParent(key, allowed, data)} onChange={() => setAllowed(current => toggleScopedPermission(current, key, data))}/>{text}</label>)}</div>)}{keys.length > 0 && <button type="button" className="primary-button" onClick={save}>Lưu phân quyền</button>}</fieldset>}
    {data && !keys.length && !fixed && <p>Trang này chưa có quyền riêng trong danh mục máy chủ.</p>}
  </section></EmployeeProfileModal>
}
