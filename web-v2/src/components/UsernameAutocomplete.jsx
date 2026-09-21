import { Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'

export default function UsernameAutocomplete({
  label, options = [], value = '', values = [], onChange, onToggle, multiple = false,
  placeholder = 'Tìm theo username…',
}) {
  const [query, setQuery] = useState('')
  const normalized = query.trim().toLowerCase()
  const matches = useMemo(() => options.filter((item) => {
    const username = String(item.username || '').toLowerCase()
    const role = String(item.role || '').toLowerCase()
    return !normalized || username.includes(normalized) || role.includes(normalized)
  }).slice(0, 80), [normalized, options])

  const choose = (username) => {
    if (multiple) onToggle?.(username)
    else {
      onChange?.(username)
      setQuery(username)
    }
  }

  return <div className="username-autocomplete">
    {label && <strong>{label}</strong>}
    <div className="username-autocomplete-search"><Search size={15}/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={placeholder}/>{query && <button type="button" aria-label="Xóa tìm kiếm" onClick={() => setQuery('')}><X size={14}/></button>}</div>
    {!multiple && value && <div className="username-autocomplete-current">Đã chọn: <b>{value}</b></div>}
    <div className="username-autocomplete-options" role="listbox" aria-multiselectable={multiple || undefined}>
      {matches.map((item) => {
        const selected = multiple ? values.includes(item.username) : value === item.username
        return <button type="button" role="option" aria-selected={selected} className={selected ? 'selected' : ''} key={item.username} onClick={() => choose(item.username)}><span>{item.username}</span>{item.role && <small>{item.role === 'quanly' ? 'Quản lý' : item.role}</small>}</button>
      })}
      {!matches.length && <span className="username-autocomplete-empty">Không tìm thấy username phù hợp.</span>}
    </div>
  </div>
}
