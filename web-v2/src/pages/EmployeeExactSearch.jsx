import { Search, X } from 'lucide-react'
import { useEffect, useMemo, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'

const normalize = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

function setNativeInput(input, value) {
  if (!input) return
  const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set
  if (setter) setter.call(input, value)
  else input.value = value
  input.dispatchEvent(new Event('input', { bubbles: true }))
}

export default function EmployeeExactSearch() {
  const [target, setTarget] = useState(null)
  const [employees, setEmployees] = useState([])
  const [query, setQuery] = useState('')

  useEffect(() => {
    let active = true
    veraApi.staff().then((result) => {
      if (active) setEmployees(Array.isArray(result.employees) ? result.employees : [])
    }).catch(() => {})
    return () => { active = false }
  }, [])

  useEffect(() => {
    let ownedHost = null
    const sync = () => {
      const toolbar = document.querySelector('.staff-control-panel .staff-toolbar')
      const original = toolbar?.querySelector('.staff-search')
      if (!toolbar || !original) return
      original.classList.add('staff-search-original-hidden')
      let host = toolbar.querySelector('[data-exact-staff-search="true"]')
      if (!host) {
        host = document.createElement('div')
        host.dataset.exactStaffSearch = 'true'
        toolbar.insertBefore(host, original)
        ownedHost = host
      }
      setTarget((current) => current === host ? current : host)
    }
    sync()
    const observer = new MutationObserver(sync)
    observer.observe(document.body, { childList: true, subtree: true })
    return () => {
      observer.disconnect()
      document.querySelector('.staff-search-original-hidden')?.classList.remove('staff-search-original-hidden')
      if (ownedHost?.isConnected) ownedHost.remove()
    }
  }, [])

  const names = useMemo(() => employees.map((employee) => ({
    username: String(employee.username || '').trim(),
    fullName: String(employee.full_name || '').trim(),
  })).filter((item) => item.username), [employees])

  const apply = (value) => {
    setQuery(value)
    const original = document.querySelector('.staff-control-panel .staff-search input')
    if (!value.trim()) {
      setNativeInput(original, '')
      return
    }
    const key = normalize(value)
    const exact = names.find((item) => normalize(item.username) === key || (item.fullName && normalize(item.fullName) === key))
    setNativeInput(original, exact?.username || '__VERA_EXACT_EMPLOYEE_NOT_FOUND__')
  }

  if (!target) return <style>{`.staff-search-original-hidden{display:none!important}`}</style>

  return createPortal(<>
    <style>{`
      .staff-search-original-hidden{display:none!important}
      .staff-exact-search{display:flex;align-items:center;gap:8px;min-width:min(360px,100%);padding:0 12px;border:1px solid #d9e1dc;border-radius:10px;background:#fff}
      .staff-exact-search input{width:100%;min-width:0;border:0!important;outline:0!important;box-shadow:none!important;background:transparent!important;padding:11px 0!important}
      .staff-exact-search button{border:0;background:transparent;padding:5px;color:#64736b;cursor:pointer;display:flex}
      @media(max-width:760px){.staff-exact-search{width:100%;min-width:0}}
    `}</style>
    <div className="staff-exact-search">
      <Search size={17} aria-hidden="true" />
      <input
        type="search"
        value={query}
        onChange={(event) => apply(event.target.value)}
        placeholder="Chọn hoặc nhập chính xác tên nhân viên"
        list="vera-exact-employee-names"
        aria-label="Tìm chính xác tên nhân viên"
      />
      {query && <button type="button" onClick={() => apply('')} aria-label="Xóa tìm kiếm"><X size={16} /></button>}
      <datalist id="vera-exact-employee-names">
        {names.map((item) => <option key={item.username} value={item.username}>{item.fullName || item.username}</option>)}
      </datalist>
    </div>
  </>, target)
}
