import { CalendarDays } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { ISO_DATE, formatVeraDate, parseVeraDate } from '../lib/veraDate'

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
    textRef.current?.setCustomValidity('')
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
    textRef.current?.setCustomValidity((!iso || outOfRange) ? 'Ngày phải đúng định dạng dd/mm/yyyy và nằm trong phạm vi cho phép.' : '')
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
    const picker = pickerRef.current
    if (!picker) return
    try {
      if (typeof picker.showPicker === 'function') {
        picker.showPicker()
        return
      }
    } catch {
      // Safari may expose showPicker but reject it for a programmatic trigger.
    }
    picker.click()
  }

  return <span className={`vera-date-input ${invalid ? 'invalid' : ''} ${className}`.trim()}>
    <input
      ref={textRef}
      id={id}
      name={name}
      type="text"
      inputMode="numeric"
      pattern="[0-9]{2}/[0-9]{2}/[0-9]{4}"
      maxLength={10}
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
    <input ref={pickerRef} className="vera-native-date-picker" type="date" tabIndex={-1} value={ISO_DATE.test(String(value || '')) ? value : ''} min={min} max={max} disabled={disabled || readOnly} onChange={pickDate} aria-label={`Lịch ${ariaLabel || 'ngày'}`} />
  </span>
}
