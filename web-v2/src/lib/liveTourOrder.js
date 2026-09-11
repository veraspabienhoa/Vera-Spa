// The board displays Vietnam dates, never locale-dependent MM/DD dates.
export function tourStartOrder(value) {
  const raw = String(value ?? '').trim()
  if (!raw) return [0, 0]
  const local = raw.match(/^(\d{2})\/(\d{2})\/(\d{4}) (\d{2}):(\d{2})(?::(\d{2}))?$/)
  const iso = local ? `${local[3]}-${local[2]}-${local[1]}T${local[4]}:${local[5]}:${local[6] || '00'}+07:00` : raw
  const parsed = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}/.test(iso) ? Date.parse(iso) : NaN
  if (local && Number.isFinite(parsed) && new Date(parsed + 7 * 3600000).toISOString().slice(0, 19) !== iso.slice(0, 19)) return [2, 0]
  return Number.isFinite(parsed) ? [1, Math.floor(parsed / 1000)] : [2, 0]
}

export function employeeTourStart(employee) {
  if (!employee.service && !employee.status && Object.hasOwn(employee.last_assignment_display || {}, 'TG bắt đầu thực hiện')) {
    return employee.last_assignment_display['TG bắt đầu thực hiện']
  }
  return String(employee.request || '').trim().toLowerCase() === 'yc' ? '' : employee.started_at || ''
}
