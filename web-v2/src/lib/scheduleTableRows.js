import { formatVeraDate, formatVeraDateTime } from './veraDate.js'

// Hide the internal HC rules label at display/export boundaries only.
export function violationDisplayText(value) {
  return String(value ?? '').split('·')
    .filter(part => !/^Nội quy HC(?:\s+v\d+)?$/iu.test(part.trim()))
    .join('·').trim()
}

export function monthlyStatisticsExportRows(statistics, label, canViewEmployee, canViewDepartment, unavailable = false) {
  const values = (item, name, allowed) => [name, item.workDays, item.offDays, item.ca1Days, item.ca2Days,
    Number(item.overtimeHours.toFixed(2)), unavailable || !allowed ? '—' : item.violations, unavailable || !allowed ? '—' : item.penalty]
  return [...statistics.rows.map(item => values(item, item.name, canViewEmployee(item.username))),
    values(statistics.departmentTotal, `Tổng bộ phận ${label}`, canViewDepartment)]
}

export function violationExportRows(rows) {
  return [...rows.map(row => [row.employee_name, formatVeraDate(row.violation_date), violationDisplayText(row.reason), row.hc_late_approved && row.hc_late_minutes != null ? Number(row.hc_late_minutes) : null, Number(row.amount || 0),
    row.hc_late_approval_eligible ? `${row.hc_late_approved ? 'Đi trễ có phép' : 'Đi trễ không phép'} · Căn cứ gốc: ${violationDisplayText(row.note)}` : violationDisplayText(row.note), row.updated_by || '', formatVeraDateTime(row.created_at)]),
  ['Tổng', '', '', null, rows.reduce((sum, row) => sum + Number(row.amount || 0), 0), '', '', '']]
}
