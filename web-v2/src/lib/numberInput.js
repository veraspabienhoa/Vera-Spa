export function numberInputDisplayValue(value) {
  if (value === '' || value === null || value === undefined) return ''
  const numericValue = Number(value)
  return Number.isFinite(numericValue) && numericValue === 0 ? '' : value
}
