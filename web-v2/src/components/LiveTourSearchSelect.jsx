import { useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal, flushSync } from 'react-dom'
import { advanceBookingField } from '../lib/advanceBookingField'
import { searchTextMatches, scrollSearchOption } from '../lib/searchText'
import './LiveTourSearchSelect.css'
import ClearableSearchInput from './ClearableSearchInput'

export default function LiveTourSearchSelect({ label, value, options, onChange, placeholder = 'Tìm và chọn…', required = false, disabled = false, clearOnSelect = false, filterOption, searchValue, onSearch, hideLabel = false, className = '', emptyLabel = 'Để trống', inputMode, advanceOnSelect = false, invalid = false }) {
  const id = useId(), root = useRef(null), input = useRef(null), menu = useRef(null), side = useRef(null)
  const typing = useRef(false)
  const selected = options.find((item) => item.value === value)
  const freeSearch = typeof searchValue === 'string'
  const [localQuery, setQuery] = useState(selected?.label || '')
  const query = freeSearch ? searchValue : localQuery
  const [open, setOpen] = useState(false)
  const [index, setIndex] = useState(0)
  const [position, setPosition] = useState({ left: 0, top: 0, width: 240 })
  useEffect(() => { if (!typing.current) setQuery(selected?.label || ''); typing.current = false }, [value, selected?.label])
  const matches = options.filter((option) => filterOption ? filterOption(option, query) : searchTextMatches([option.label, option.detail], query))
  const activeIndex = Math.min(index, Math.max(0, matches.length - 1))
  const close = () => { setOpen(false); side.current = null }
  const choose = (item) => {
    flushSync(() => { onChange(item.value); setQuery(clearOnSelect ? '' : item.label); close(); setIndex(0) })
    if (advanceOnSelect) advanceBookingField(input.current)
  }

  useLayoutEffect(() => {
    if (!open || disabled) return
    let frame
    const place = () => {
      const rect = input.current?.getBoundingClientRect()
      if (!rect) return
      const view = window.visualViewport
      const width = view?.width || window.innerWidth, height = view?.height || window.innerHeight
      const top = view?.offsetTop || 0, left = view?.offsetLeft || 0
      const below = top + height - rect.bottom - 8, above = rect.top - top - 8
      side.current ??= below < 180 && above > below ? 'above' : 'below'
      const room = side.current === 'above' ? above : below
      const menuHeight = Math.max(40, Math.min(height - 16, Math.max(80, room), 360))
      const menuWidth = Math.min(Math.max(rect.width, 240), width - 16)
      setPosition({ left: Math.max(left + 8, Math.min(rect.left, left + width - menuWidth - 8)),
        top: Math.max(top + 8, Math.min(side.current === 'above' ? rect.top - menuHeight - 4 : rect.bottom + 4, top + height - menuHeight - 8)),
        width: menuWidth, maxHeight: menuHeight })
    }
    const schedule = () => { window.cancelAnimationFrame(frame); frame = window.requestAnimationFrame(place) }
    place()
    window.addEventListener('resize', schedule)
    window.addEventListener('scroll', schedule, true)
    window.visualViewport?.addEventListener('resize', schedule)
    window.visualViewport?.addEventListener('scroll', schedule)
    return () => {
      window.cancelAnimationFrame(frame)
      window.removeEventListener('resize', schedule)
      window.removeEventListener('scroll', schedule, true)
      window.visualViewport?.removeEventListener('resize', schedule)
      window.visualViewport?.removeEventListener('scroll', schedule)
    }
  }, [open, disabled])

  useEffect(() => {
    if (open) scrollSearchOption(menu.current, menu.current?.querySelector(`[id="${id}-${activeIndex}"]`))
  }, [activeIndex, id, open])

  return <div className={`live-tour-search-select ${className}`} ref={root} onBlur={(event) => {
    if (!root.current?.contains(event.relatedTarget) && !menu.current?.contains(event.relatedTarget)) { close(); if (!freeSearch) setQuery(selected?.label || '') }
  }}>
    {!hideLabel && <label htmlFor={id}>{label}</label>}
    <ClearableSearchInput ref={input} onClear={() => { onChange(''); onSearch?.(''); setQuery(''); setIndex(0) }} data-booking-step={advanceOnSelect ? true : undefined} aria-invalid={invalid || undefined} id={id} type={freeSearch ? 'search' : 'text'} inputMode={inputMode} aria-label={hideLabel ? label : undefined} role="combobox" aria-autocomplete="list" aria-expanded={open && !disabled} aria-controls={`${id}-options`} aria-activedescendant={open && matches[activeIndex] ? `${id}-${activeIndex}` : undefined} autoComplete="off" value={query} required={required} disabled={disabled} placeholder={placeholder}
      onFocus={() => { setOpen(true); if (!freeSearch) setQuery(''); setIndex(0) }}
      onChange={(event) => { typing.current = Boolean(value); setQuery(event.target.value); onSearch?.(event.target.value); setOpen(true); setIndex(0); if (value && !freeSearch) onChange('') }}
      onKeyDown={(event) => {
        if (event.key === 'ArrowDown' || event.key === 'ArrowUp') { event.preventDefault(); setOpen(true); setIndex((current) => Math.max(0, Math.min(matches.length - 1, current + (event.key === 'ArrowDown' ? 1 : -1)))) }
        if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); if (!freeSearch) setQuery(selected?.label || '') }
        if (event.key === 'Enter' && open) { event.preventDefault(); if (matches[activeIndex]) choose(matches[activeIndex]) }
      }}/>
    {open && !disabled && createPortal(<div ref={menu} className="tour-search-popup tour-search-scroll" style={{ left: position.left, top: position.top, width: position.width, maxHeight: position.maxHeight }} onMouseDown={(event) => event.preventDefault()}>
      <div role="listbox" id={`${id}-options`} aria-label={label}>
        {!required && <button type="button" tabIndex={-1} role="option" aria-selected={!value} onClick={() => { if (freeSearch) onSearch?.(''); choose({ value: '', label: '' }) }}>{emptyLabel}</button>}
        {matches.map((item, i) => {
          return <button type="button" tabIndex={-1} role="option" id={`${id}-${i}`} key={item.value} aria-selected={value === item.value} className={`${i === activeIndex ? 'highlighted' : ''} ${item.className || ''}`} onClick={() => choose(item)}><span className="tour-select-option-heading"><strong>{item.label}</strong>{item.badge && <strong className="tour-ticket-badge">{item.badge}</strong>}</span>{item.detail && <small>{item.detail}</small>}</button>
        })}
        {!matches.length && <p>Không có kết quả phù hợp.</p>}
      </div>
    </div>, document.body)}
  </div>
}
