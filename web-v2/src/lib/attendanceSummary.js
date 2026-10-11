import { formatVeraDate, parseVeraDate } from './veraDate.js'

export const ATTENDANCE_SUMMARY_FILTERS = [
  { id: 'all', label: 'Bản ghi chấm công' },
  { id: 'breaks', label: 'Đủ cặp nghỉ giữa ca' },
  { id: 'over', label: 'Vi phạm nghỉ / ra ngoài' },
  { id: 'incomplete', label: 'Đang nghỉ / thiếu FaceID vào lại' },
]

export function deadlineMsFor(item) {
  if (item.break_return_deadline_iso) {
    let raw = String(item.break_return_deadline_iso).trim().replace(' ', 'T')
    const parts = raw.match(/^(\d{4}-\d{2}-\d{2})T(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?$/i)
    if (parts && formatVeraDate(parts[1]) && Number(parts[2]) < 24 && Number(parts[3]) < 60 && Number(parts[4] || 0) < 60) {
      if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) raw += '+07:00'
      const value = new Date(raw).getTime()
      if (Number.isFinite(value)) return value
    }
  }
  const day = parseVeraDate(formatVeraDate(item.date))
  const clock = String(item.break_return_deadline || '').trim()
  const parts = clock.match(/^(\d{2}):(\d{2})(?::(\d{2})(?:\.\d+)?)?$/)
  if (!day || !parts || Number(parts[1]) >= 24 || Number(parts[2]) >= 60 || Number(parts[3] || 0) >= 60) return NaN
  const value = new Date(`${day}T${clock}+07:00`).getTime()
  return Number.isFinite(value) ? value : NaN
}

// Keep the existing card definitions. Categories overlap: a completed or
// still-open break can also be overdue. These are not penalty eligibility rules.
export function matchesAttendanceSummary(item, filter, nowMs) {
  if (filter === 'all') return true
  const restricted = Boolean(item.break_restricted_reason)
  if (filter === 'breaks') return !restricted && Boolean(item.break_out && item.break_in)
  if (filter === 'incomplete') return !restricted && Boolean(item.break_enabled && (!item.break_out || !item.break_in))
  if (filter === 'over') {
    if (restricted) return Boolean(item.break_out)
    if (Number(item.break_over_minutes || 0) > 0 || Number(item.break_return_late_minutes || 0) > 0) return true
    if (!item.break_out || item.break_in) return false
    const deadline = deadlineMsFor(item)
    return Number.isFinite(deadline) && deadline < nowMs
  }
  return false
}

export function attendanceSummary(records, nowMs) {
  const counts = { all: records.length, breaks: 0, over: 0, incomplete: 0 }
  for (const item of records) {
    for (const filter of ['breaks', 'over', 'incomplete']) {
      if (matchesAttendanceSummary(item, filter, nowMs)) counts[filter] += 1
    }
  }
  return counts
}
