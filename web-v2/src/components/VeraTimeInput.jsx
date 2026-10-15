import { useEffect, useRef, useState } from 'react'
import { Clock } from 'lucide-react'
import './VeraTimeInput.css'

export default function VeraTimeInput({ value = '', onChange, required = false, disabled = false, 'aria-label': label = 'Giờ' }) {
  const [text, setText] = useState(value)
  const [open, setOpen] = useState(false)
  const input = useRef(null)
  const emitted = useRef(value)
  useEffect(() => {
    if (value !== emitted.current) { setText(value); emitted.current = value; input.current?.setCustomValidity('') }
  }, [value])
  const change = value => {
    const raw = /^\d{4}$/.test(value) ? `${value.slice(0, 2)}:${value.slice(2)}` : value
    setText(raw)
    const valid = /^([01]\d|2[0-3]):[0-5]\d$/.test(raw)
    input.current?.setCustomValidity(raw && !valid ? 'Nhập giờ theo HH:mm, từ 00:00 đến 23:59.' : '')
    emitted.current = valid ? raw : ''
    onChange?.({ target: { value: emitted.current }, currentTarget: { value: emitted.current } })
  }
  const [hour = '', minute = ''] = text.split(':')
  return <span className="vera-time-input">
    <span className="vera-time-entry"><input ref={input} type="text" inputMode="numeric" placeholder="HH:mm" maxLength={5} aria-label={label} required={required} disabled={disabled} value={text} onChange={event => change(event.target.value)} onBlur={() => {
      const match = /^(\d{1,2}):(\d{1,2})$/.exec(text)
      if (match && Number(match[1]) < 24 && Number(match[2]) < 60) change(`${match[1].padStart(2, '0')}:${match[2].padStart(2, '0')}`)
    }}/><button type="button" disabled={disabled} aria-label={`Chọn ${label.toLowerCase()}`} aria-expanded={open} onClick={() => setOpen(current => !current)}><Clock size={18}/></button></span>
    {open && !disabled && <span className="vera-time-picker" onKeyDown={event => { if (event.key === 'Escape') { event.stopPropagation(); setOpen(false); input.current?.focus() } }}>
      <select aria-label={`${label} · Giờ`} value={/^\d{2}$/.test(hour) && Number(hour) < 24 ? hour : ''} onChange={event => change(`${event.target.value}:${/^\d{2}$/.test(minute) && Number(minute) < 60 ? minute : '00'}`)}><option value="" disabled>Giờ</option>{Array.from({length:24}, (_, i) => String(i).padStart(2, '0')).map(n => <option key={n}>{n}</option>)}</select>
      <span>:</span>
      <select aria-label={`${label} · Phút`} value={/^\d{2}$/.test(minute) && Number(minute) < 60 ? minute : ''} onChange={event => change(`${/^\d{2}$/.test(hour) && Number(hour) < 24 ? hour : '00'}:${event.target.value}`)}><option value="" disabled>Phút</option>{Array.from({length:60}, (_, i) => String(i).padStart(2, '0')).map(n => <option key={n}>{n}</option>)}</select>
      <button type="button" onClick={() => { setOpen(false); input.current?.focus() }}>Xong</button>
    </span>}
  </span>
}
