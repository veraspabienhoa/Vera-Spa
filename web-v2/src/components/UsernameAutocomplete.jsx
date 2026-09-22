import { Search, X } from 'lucide-react'
import { useMemo, useState } from 'react'

export default function UsernameAutocomplete({
  label, options = [], value = '', values = [], onChange, onToggle, multiple = false,
  placeholder = 'Tìm theo username…', searchOnly = false, namesOnly = false,
}) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const normalized = query.trim().toLowerCase()
  const matches = useMemo(() => options.filter((item) => {
    const username = String(item.username || '').toLowerCase()
    const role = String(item.role || '').toLowerCase()
    const fullName = String(item.full_name || item.name || '').toLowerCase()
    return !normalized || username.includes(normalized) || fullName.includes(normalized) || (!namesOnly && role.includes(normalized))
  }).slice(0, 80), [normalized, options, namesOnly])

  const choose = (username) => {
    if (multiple) onToggle?.(username)
    else {
      onChange?.(username)
      setQuery(username)
      setOpen(false)
    }
  }

  return <div className="username-autocomplete">
    {label && <strong>{label}</strong>}
    <div className="username-autocomplete-search"><Search size={15}/><input value={query} onChange={(event) => { setQuery(event.target.value); setOpen(true); if (searchOnly || namesOnly) onChange?.('') }} onKeyDown={event => { if (event.key === 'Escape') setOpen(false) }} placeholder={placeholder}/>{query && <button data-ui-key="u-72640efa4074" type="button" aria-label="Xóa tìm kiếm" onClick={() => { setQuery(''); setOpen(false); if (searchOnly || namesOnly) onChange?.('') }}><X size={14}/></button>}</div>
    {!multiple && value && <div className="username-autocomplete-current">Đã chọn: <b>{value}</b></div>}
    {(!searchOnly || (open && normalized)) && <div className="username-autocomplete-options" role="listbox" aria-multiselectable={multiple || undefined}>
      {matches.map((item) => {
        const selected = multiple ? values.includes(item.username) : value === item.username
        return <button data-ui-key="u-f843b394eb3a" type="button" role="option" aria-selected={selected} className={selected ? 'selected' : ''} key={item.username} onClick={() => choose(item.username)}><span>{item.username}</span>{item.role && <small>{item.role === 'quanly' ? 'Quản lý' : item.role}</small>}</button>
      })}
      {!matches.length && <span className="username-autocomplete-empty">Không tìm thấy username phù hợp.</span>}
    </div>}
  </div>
}
