import { CalendarDays } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const VN_DATE = /^(\d{2})\/(\d{2})\/(\d{4})$/

export function formatVeraDate(value) {
  const raw = String(value || '').trim()
  const iso = raw.match(ISO_DATE)
  if (iso) return `${iso[3]}/${iso[2]}/${iso[1]}`
  return VN_DATE.test(raw) ? raw : ''
}

export function parseVeraDate(value) {
  const match = String(value || '').trim().match(VN_DATE)
  if (!match) return ''
  const iso = `${match[3]}-${match[2]}-${match[1]}`
  const parsed = new Date(`${iso}T00:00:00`)
  if (Number.isNaN(parsed.getTime())) return ''
  if (parsed.getFullYear() !== Number(match[3]) || parsed.getMonth() + 1 !== Number(match[2]) || parsed.getDate() !== Number(match[1])) return ''
  return iso
}

function typedDate(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 8)
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('/')
}

export default function VeraDateInput({
  value = '', onChange, min = '', max = '', disabled = false, readOnly = false,
  required = false, className = '', name, id, 'aria-label': ariaLabel,
}) {
  const [display, setDisplay] = useState(() => formatVeraDate(value))
  const [invalid, setInvalid] = useState(false)
  const pickerRef = useRef(null)
  const textRef = useRef(null)

  useEffect(() => {
    setDisplay(formatVeraDate(value))
    setInvalid(false)
  }, [value])

  const emit = (nextValue) => onChange?.({
    target: { value: nextValue, name },
    currentTarget: { value: nextValue, name },
  })

  const validateAndEmit = (nextDisplay, allowPartial = true) => {
    if (!nextDisplay) {
      setInvalid(false)
      textRef.current?.setCustomValidity('')
      emit('')
      return
    }
    const iso = parseVeraDate(nextDisplay)
    const complete = nextDisplay.length === 10
    const outOfRange = Boolean(iso && ((min && iso < min) || (max && iso > max)))
    const hasError = (complete && !iso) || outOfRange || (!allowPartial && !iso)
    setInvalid(hasError)
    textRef.current?.setCustomValidity(hasError ? 'Ngày phải đúng định dạng dd/mm/yyyy và nằm trong phạm vi cho phép.' : '')
    if (iso && !outOfRange) emit(iso)
  }

  const changeText = (event) => {
    const nextDisplay = typedDate(event.target.value)
    setDisplay(nextDisplay)
    validateAndEmit(nextDisplay)
  }

  const pickDate = (event) => {
    const iso = event.target.value
    setDisplay(formatVeraDate(iso))
    setInvalid(false)
    textRef.current?.setCustomValidity('')
    emit(iso)
  }

  const openPicker = () => {
    if (disabled || readOnly) return
    if (typeof pickerRef.current?.showPicker === 'function') pickerRef.current.showPicker()
    else pickerRef.current?.click()
  }

  return <span className={`vera-date-input ${invalid ? 'invalid' : ''} ${className}`.trim()}>
    <input
      ref={textRef}
      id={id}
      name={name}
      type="text"
      inputMode="numeric"
      autoComplete="off"
      placeholder="dd/mm/yyyy"
      value={display}
      disabled={disabled}
      readOnly={readOnly}
      required={required}
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      onChange={changeText}
      onBlur={() => validateAndEmit(display, false)}
    />
    {!readOnly && <button type="button" className="vera-date-picker-button" disabled={disabled} onClick={openPicker} aria-label={`Chọn ${ariaLabel || 'ngày'}`}><CalendarDays size={16} /></button>}
    <input ref={pickerRef} className="vera-native-date-picker" type="date" tabIndex={-1} value={ISO_DATE.test(String(value || '')) ? value : ''} min={min} max={max} disabled={disabled || readOnly} onChange={pickDate} aria-hidden="true" />
  </span>
}
