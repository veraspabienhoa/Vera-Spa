import { CalendarDays } from 'lucide-react'
import { useEffect, useRef, useState } from 'react'

import { FILTER_CONTROL_SCOPE } from '../lib/filterControlScope'
import { ISO_DATE, formatVeraDate, parseVeraDate } from '../lib/veraDate'

function typedDate(value) {
  const digits = String(value || '').replace(/\D/g, '').slice(0, 8)
  return [digits.slice(0, 2), digits.slice(2, 4), digits.slice(4, 8)].filter(Boolean).join('-')
}

export default function VeraDateInput({
  value = '', onChange, min = '', max = '', disabled = false, readOnly = false,
  clearOnFocus, clearable = false, required = false, className = '', name, id, onDraftValidity, 'aria-label': ariaLabel,
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
      onDraftValidity?.(false)
      setInvalid(false)
      textRef.current?.setCustomValidity('')
      emit('')
      return
    }
    const iso = parseVeraDate(nextDisplay)
    const complete = nextDisplay.length === 10
    const outOfRange = Boolean(iso && ((min && iso < min) || (max && iso > max)))
    const hasError = (complete && !iso) || outOfRange || (!allowPartial && !iso)
    onDraftValidity?.(Boolean(iso && !outOfRange))
    setInvalid(hasError)
    textRef.current?.setCustomValidity((!iso || outOfRange) ? 'Ngày phải đúng định dạng dd-mm-yyyy và nằm trong phạm vi cho phép.' : '')
    if (iso && !outOfRange) emit(iso)
  }

  const beginDateEdit = (event) => {
    const filterField = clearOnFocus ?? Boolean(event.currentTarget.closest(FILTER_CONTROL_SCOPE))
    if (!filterField || disabled || readOnly || !display || display !== formatVeraDate(value)) return
    // Clear the draft immediately, but apply the filter only after a complete date
    // or an intentional empty blur. Clicking alone must not trigger another load.
    setDisplay('')
    setInvalid(false)
    onDraftValidity?.(false)
    textRef.current?.setCustomValidity('Nhập ngày mới theo định dạng dd-mm-yyyy.')
  }

  const changeText = (event) => {
    const nextDisplay = typedDate(event.target.value)
    setDisplay(nextDisplay)
    validateAndEmit(nextDisplay)
  }

  const pickDate = (event) => {
    const iso = event.target.value
    onDraftValidity?.(Boolean(iso && (!min || iso >= min) && (!max || iso <= max)))
    setDisplay(formatVeraDate(iso))
    setInvalid(false)
    textRef.current?.setCustomValidity('')
    emit(iso)
  }

  const openPicker = () => {
    const picker = pickerRef.current
    if (!picker || disabled || readOnly) return
    try {
      if (typeof picker.showPicker === 'function') {
        picker.showPicker()
        return
      }
    } catch {
      // Browser may reject showPicker outside a direct activation. The native
      // input is always mounted and its direct hit-area remains available.
    }
    picker.click()
  }


  const canClear = clearable && !readOnly && Boolean(display || value)
  return <span className={`vera-date-input ${invalid ? 'invalid' : ''} ${canClear ? 'vera-date-clearable' : ''} ${className}`.trim()}>
    <input
      ref={textRef}
      id={id}
      name={name}
      type="text"
      inputMode="numeric"
      pattern="[0-9]{2}-[0-9]{2}-[0-9]{4}"
      maxLength={10}
      autoComplete="off"
      placeholder="dd-mm-yyyy"
      value={display}
      disabled={disabled}
      readOnly={readOnly}
      required={required}
      aria-label={ariaLabel}
      aria-invalid={invalid || undefined}
      onFocus={beginDateEdit}
      onClick={beginDateEdit}
      onChange={changeText}
      onBlur={() => validateAndEmit(display, false)}
    />
    {canClear && <button type="button" className="search-clear-button vera-date-clear-button" aria-label={`Clear ${ariaLabel || 'ngày'}`} disabled={disabled} onMouseDown={event => event.preventDefault()} onClick={() => { setDisplay(''); validateAndEmit('') }}>Clear</button>}
    {!readOnly && <button data-ui-key="u-c2de40025e31" type="button" className="vera-date-picker-button" disabled={disabled} onClick={openPicker} tabIndex={-1} aria-hidden="true"><CalendarDays size={16} /></button>}
    {!readOnly && <input ref={pickerRef} className="vera-native-date-picker" type="date" tabIndex={-1} value={ISO_DATE.test(String(value || '')) ? value : ''} min={min} max={max} disabled={disabled} onChange={pickDate} aria-label={`Lịch ${ariaLabel || 'ngày'}`} />}
  </span>
}
