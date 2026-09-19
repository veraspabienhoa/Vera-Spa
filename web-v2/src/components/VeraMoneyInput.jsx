const digitsOnly = (value) => String(value ?? '').replace(/\D/g, '')

function formatVeraMoney(value) {
  const digits = digitsOnly(value)
  return digits ? digits.replace(/\B(?=(\d{3})+(?!\d))/g, '.') : ''
}

export default function VeraMoneyInput({ value = '', onChange, name, className = '', max, ...props }) {
  const emit = (event) => {
    const raw = digitsOnly(event.target.value)
    const bounded = max != null && raw ? String(Math.min(Number(raw), Number(max))) : raw
    const next = bounded ? Number(bounded) : ''
    onChange?.({
      target: { value: next, name },
      currentTarget: { value: next, name },
    })
  }

  return <input
    {...props}
    name={name}
    type="text"
    inputMode="numeric"
    className={`vera-money-input ${className}`.trim()}
    value={formatVeraMoney(value)}
    onChange={emit}
  />
}
