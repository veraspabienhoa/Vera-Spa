import { useEffect, useRef, useState } from 'react'
import VeraDateInput from './VeraDateInput'

// A visible dd/mm/yyyy date plus 24-hour time; the parent still receives ISO local time.
export default function VeraDateTimeInput({ value = '', onChange, required = false, disabled = false, readOnly = false, 'aria-label': label = 'Ngày giờ' }) {
  const [date, setDate] = useState(value.slice(0, 10))
  const [time, setTime] = useState(value.slice(11, 16))
  const lastEmitted = useRef(value)
  useEffect(() => {
    if (value !== lastEmitted.current) {
      setDate(value.slice(0, 10)); setTime(value.slice(11, 16))
      lastEmitted.current = value
    }
  }, [value])
  const emit = (nextDate, nextTime) => {
    const next = nextDate && nextTime ? `${nextDate}T${nextTime}` : ''
    lastEmitted.current = next
    onChange?.({ target: { value: next }, currentTarget: { value: next } })
  }
  return <span className="vera-datetime-input">
    <VeraDateInput value={date} required={required || Boolean(time)} disabled={disabled} readOnly={readOnly} aria-label={`${label} · Ngày`} onChange={event => { setDate(event.target.value); emit(event.target.value, time) }}/>
    <input type="time" value={time} required={required || Boolean(date)} disabled={disabled} readOnly={readOnly} aria-label={`${label} · Giờ`} onChange={event => { setTime(event.target.value); emit(date, event.target.value) }}/>
  </span>
}
