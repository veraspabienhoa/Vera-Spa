import { useEffect, useId, useRef, useState } from 'react'
import { tourNameKey } from '../lib/liveTourBooking'

export default function LiveTourSearchSelect({ label, value, options, onChange, placeholder = 'Tìm và chọn…', required = false, disabled = false, clearOnSelect = false }) {
  const id = useId()
  const root = useRef(null)
  const typing = useRef(false)
  const selected = options.find((item) => item.value === value)
  const [query, setQuery] = useState(selected?.label || '')
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)
  useEffect(() => { if (!typing.current) setQuery(selected?.label || ''); typing.current = false }, [value, selected?.label])
  const matches = options.filter((option) => !query || tourNameKey(`${option.label} ${option.detail || ''}`).includes(tourNameKey(query)))
  const choose = (item) => { onChange(item.value); setQuery(clearOnSelect ? '' : item.label); setOpen(false); setIndex(0) }
  return <div className="live-tour-search-select" ref={root} onBlur={(event) => { if (!root.current?.contains(event.relatedTarget)) { setOpen(false); setQuery(selected?.label || '') } }}>
    <label htmlFor={id}>{label}</label>
    <input id={id} role="combobox" aria-autocomplete="list" aria-expanded={open} aria-controls={`${id}-options`} aria-activedescendant={open && matches[index] ? `${id}-${index}` : undefined} autoComplete="off" value={query} required={required} disabled={disabled} placeholder={placeholder}
      onFocus={() => { setOpen(true); setQuery(''); setIndex(0) }}
      onChange={(event) => { typing.current = Boolean(value); setQuery(event.target.value); setOpen(true); setIndex(0); if (value) onChange('') }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); setIndex((current) => Math.max(0, Math.min(matches.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)))) }
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); setOpen(false); setQuery(selected?.label || '') }
        if (event.key === 'Enter' && open && matches[index]) { event.preventDefault(); choose(matches[index]) }
      }}/>
    {open && <div className="live-tour-select-options" role="listbox" id={`${id}-options`}>
      {!required && <button type="button" role="option" aria-selected={!value} onMouseDown={(event) => event.preventDefault()} onClick={() => { onChange(''); setQuery(''); setOpen(false) }}>Để trống</button>}
      {matches.map((item, i) => <button type="button" role="option" id={`${id}-${i}`} key={item.value} aria-selected={value === item.value} className={i === index ? 'highlighted' : ''} onMouseDown={(event) => event.preventDefault()} onClick={() => choose(item)}><span className="tour-select-option-heading"><strong>{item.label}</strong>{item.badge && <strong className="tour-ticket-badge">{item.badge}</strong>}</span>{item.detail && <small>{item.detail}</small>}</button>)}
      {!matches.length && <p>Không có kết quả phù hợp.</p>}
    </div>}
  </div>
}
