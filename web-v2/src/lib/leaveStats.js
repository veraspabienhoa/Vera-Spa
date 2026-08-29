const normalizeText = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

const matchesEmployee = (employeeName, searchValue) => {
  const needle = normalizeText(searchValue)
  if (!needle) return true
  const shortName = String(employeeName || '').split(/\s*[-–—]\s*/, 1)[0]
  return [employeeName, shortName].some((name) => normalizeText(name) === needle)
}

const leaveGroup = (row) => {
  const key = normalizeText(`${row.leave_type || ''} ${row.leave_reason || ''}`)
  if (key.includes('khong phep')) return 'unpaid'
  if (key.includes('phat sinh')) return 'generated'
  if (key.includes('co phep') || key.includes('phep nam')) return 'paid'
  return ''
}

export const emptyLeaveDaySummary = () => ({
  total_leave: 0,
  paid: 0,
  generated: 0,
  unpaid: 0,
  total_penalty: 0,
})

export function summarizeLeaveRecordDays(records = [], employee = '') {
  return records.filter((row) => matchesEmployee(row.employee_name, employee)).reduce((summary, row) => {
    const days = Math.max(0, Number(row.calculated_days || 0))
    const group = leaveGroup(row)
    summary.total_leave += days
    if (group) summary[group] += days
    summary.total_penalty += Math.max(0, Number(row.penalty || 0))
    return summary
  }, emptyLeaveDaySummary())
}

export const formatLeaveDays = (value) => Number(value || 0).toLocaleString('vi-VN', {
  maximumFractionDigits: 2,
})
