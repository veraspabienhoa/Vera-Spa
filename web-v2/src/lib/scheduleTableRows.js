import { formatVeraDate, formatVeraDateTime } from './veraDate.js'

export function monthlyStatisticsExportRows(statistics, label, canViewEmployee, canViewDepartment, unavailable = false) {
  const values = (item, name, allowed) => [name, item.workDays, item.offDays, item.ca1Days, item.ca2Days,
    Number(item.overtimeHours.toFixed(2)), unavailable || !allowed ? '—' : item.violations, unavailable || !allowed ? '—' : item.penalty]
  return [...statistics.rows.map(item => values(item, item.name, canViewEmployee(item.username))),
    values(statistics.departmentTotal, `Tổng bộ phận ${label}`, canViewDepartment)]
}

export function violationExportRows(rows) {
  return [...rows.map(row => [row.employee_name, formatVeraDate(row.violation_date), row.reason, Number(row.amount || 0),
    row.note || '', row.updated_by || '', formatVeraDateTime(row.created_at)]),
  ['Tổng', '', '', rows.reduce((sum, row) => sum + Number(row.amount || 0), 0), '', '', '']]
}
