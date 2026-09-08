import { Search } from 'lucide-react'
import { useEffect, useId, useMemo, useRef, useState } from 'react'
import { employeeOptions, resolveEmployeeName, shortEmployeeName } from '../lib/employeeSearch'
import './EmployeeSelector.css'

/**
 * The native search/datalist used by Đăng ký nghỉ / Danh sách.
 * Filters receive the search text and use matchesEmployeeName. Assignment
 * fields opt into selectionOnly and receive only a unique allowed username.
 * Each caller supplies its existing authorized/department-specific options.
 */
export default function EmployeeSelector({
  employees = [], value = '', onChange, label = 'Tên nhân viên',
  disabled = false, required = false, selectionOnly = false,
  className = '', inputProps = {}, valueInputProps = {},
}) {
  const id = useId()
  const names = useMemo(() => employeeOptions(employees), [employees])
  const [draft, setDraft] = useState(value)
  const emitted = useRef(value)
  const inputRef = useRef(null)
  const composing = useRef(false)

  useEffect(() => {
    if (value !== emitted.current) setDraft(value)
    emitted.current = value
  }, [value])

  useEffect(() => {
    inputRef.current?.setCustomValidity(selectionOnly && draft && !resolveEmployeeName(names, draft)
      ? 'Vui lòng chọn đúng một nhân viên trong danh sách.' : '')
  }, [draft, names, selectionOnly])

  const publish = (text) => {
    const next = selectionOnly ? resolveEmployeeName(names, text) : text
    emitted.current = next
    onChange?.(next)
  }

  return <label className={`employee-search-field vera-employee-selector ${className}`} data-employee-selector="true">
    <span><Search size={15} aria-hidden="true" /> {label}</span>
    <input
      {...inputProps}
      ref={inputRef}
      className="vera-employee-input"
      type="search"
      value={draft}
      onChange={(event) => {
        setDraft(event.target.value)
        if (!composing.current) publish(event.target.value)
      }}
      onCompositionStart={() => { composing.current = true }}
      onCompositionEnd={(event) => {
        composing.current = false
        setDraft(event.currentTarget.value)
        publish(event.currentTarget.value)
      }}
      onBlur={() => {
        if (!selectionOnly) return
        const resolved = resolveEmployeeName(names, draft)
        if (resolved) setDraft(resolved)
      }}
      placeholder="Chọn hoặc nhập đúng tên nhân viên"
      aria-label={inputProps['aria-label'] || label}
      list={`${id}-employees`}
      autoComplete="off"
      disabled={disabled}
      required={required}
    />
    <datalist id={`${id}-employees`}>
      {names.map((name) => <option key={name} value={name}>{shortEmployeeName(name)}</option>)}
    </datalist>
    {selectionOnly && <input {...valueInputProps} type="hidden" data-employee-value="true" value={value} />}
  </label>
}
