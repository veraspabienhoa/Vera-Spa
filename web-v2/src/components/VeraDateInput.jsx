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
  const lastEmitted = useRef(value)
  const focusCleared = useRef(false)
  const openingPicker = useRef(false)

  useEffect(() => {
    setDisplay(formatVeraDate(value))
    setInvalid(false)
    textRef.current?.setCustomValidity('')
    lastEmitted.current = value
    focusCleared.current = false
  }, [value])

  const emit = (nextValue) => {
    lastEmitted.current = nextValue
    onChange?.({ target: { value: nextValue, name }, currentTarget: { value: nextValue, name } })
  }

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
    openingPicker.current = false
    const filterField = clearOnFocus ?? Boolean(event.currentTarget.closest(FILTER_CONTROL_SCOPE))
    if (!filterField || disabled || readOnly || !display || display !== formatVeraDate(value)) return
    // Clear the draft immediately, but apply the filter only after a complete date
    // or an intentional empty blur. Clicking alone must not trigger another load.
    focusCleared.current = true
    setDisplay('')
    setInvalid(false)
    onDraftValidity?.(false)
    textRef.current?.setCustomValidity('Nhập ngày mới theo định dạng dd-mm-yyyy.')
  }

  const changeText = (event) => {
    focusCleared.current = false
    const nextDisplay = typedDate(event.target.value)
    setDisplay(nextDisplay)
    validateAndEmit(nextDisplay)
  }

  const pickDate = (event) => {
    focusCleared.current = false
    const iso = event.target.value
    setDisplay(formatVeraDate(iso))
    validateAndEmit(formatVeraDate(iso), false)
  }

  const restoreFocusClearedDraft = () => {
    // Moving to the calendar abandons only the automatic focus placeholder.
    // Preserve any genuinely typed partial draft if the user cancels the picker.
    if (!focusCleared.current) return
    focusCleared.current = false
    setDisplay(formatVeraDate(value))
    const valid = Boolean(formatVeraDate(value) && (!min || value >= min) && (!max || value <= max))
    setInvalid(Boolean(value) && !valid)
    textRef.current?.setCustomValidity(value && !valid ? 'Ngày phải đúng định dạng dd-mm-yyyy và nằm trong phạm vi cho phép.' : '')
    onDraftValidity?.(valid)
  }

  const openPicker = (event) => {
    const picker = pickerRef.current
    if (!picker || disabled || readOnly) return
    openingPicker.current = false
    try {
      // Focus is also the native date-picker activation path on older Safari.
      // Keep it synchronous and leave the native click's default action intact.
      picker.focus({ preventScroll: true })
      if (typeof picker.showPicker === 'function') {
        picker.showPicker()
      } else if (event.currentTarget !== picker) {
        picker.click()
      }
    } catch {
      // Browser may reject showPicker outside a direct activation. The native
      // hit target still gets its default action; never recursively click it.
      if (event.currentTarget !== picker) picker.click()
    }
    restoreFocusClearedDraft()
  }

  const blurText = event => {
    const next = event.relatedTarget
    const pickerGesture = openingPicker.current
    openingPicker.current = false
    if (pickerGesture || next === pickerRef.current || next?.closest('.vera-date-picker-button') === pickerRef.current?.previousElementSibling) return
    const intentionalEmptyBlur = focusCleared.current
    focusCleared.current = false
    // Explicit changes/Clear may also change a preset or repair parent validity,
    // even for the same ISO value. Skip only their already-committed blur, before
    // both validity reporting and emission, to avoid a second filter/load.
    const committed = lastEmitted.current
    const withinRange = !committed || ((!min || committed >= min) && (!max || committed <= max))
    if (!intentionalEmptyBlur && !invalid && withinRange && textRef.current?.validity.valid && display === formatVeraDate(committed)) return
    validateAndEmit(display, false)
  }

  const pickerKeyDown = event => {
    if (!['Enter', ' '].includes(event.key) && !(event.altKey && event.key === 'ArrowDown')) return
    event.preventDefault()
    pickerRef.current?.click()
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
      onBlur={blurText}
    />
    {canClear && <button type="button" className="search-clear-button vera-date-clear-button" aria-label={`Clear ${ariaLabel || 'ngày'}`} disabled={disabled} onMouseDown={event => event.preventDefault()} onClick={() => { focusCleared.current = false; setDisplay(''); validateAndEmit('') }}>Clear</button>}
    {!readOnly && <button data-ui-key="u-c2de40025e31" type="button" className="vera-date-picker-button" disabled={disabled} onClick={openPicker} tabIndex={-1} aria-hidden="true"><CalendarDays size={16} /></button>}
    {!readOnly && <input ref={pickerRef} className="vera-native-date-picker" type="date" tabIndex={0} value={ISO_DATE.test(String(value || '')) ? value : ''} min={min} max={max} disabled={disabled} onChange={pickDate} onClick={openPicker} onKeyDown={pickerKeyDown} onFocus={restoreFocusClearedDraft} onPointerDown={() => { openingPicker.current = true }} onPointerUp={() => { openingPicker.current = false }} onPointerCancel={() => { openingPicker.current = false }} aria-label={`Lịch ${ariaLabel || 'ngày'}`} />}
  </span>
}
