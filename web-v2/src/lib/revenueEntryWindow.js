export function revenueEntryDays(data, scope, target, role = '') {
  if (role === 'admin') return null
  const policy = data?.revenue_entry_windows || {}
  const find = (items, key) => Object.entries(items || {}).find(([name]) => name.trim().toLowerCase() === String(key).trim().toLowerCase())
  const account = scope === 'account' ? find(policy.accounts, target) : null
  const group = find(policy.roles, scope === 'role' ? target : role)
  return account ? account[1] : group ? group[1] : null
}

export function revenueEntryWindowValue(value) {
  if (value === null) return null
  const days = Number(value)
  if (!String(value).trim() || !Number.isInteger(days) || days < 1 || days > 36500) throw new Error('Số ngày phải là số nguyên từ 1 đến 36500.')
  return days
}

export function revenueEntryDateAllowed(value, window) {
  return Boolean(value && (!window?.min_date || value >= window.min_date) && (!window?.max_date || value <= window.max_date))
}
