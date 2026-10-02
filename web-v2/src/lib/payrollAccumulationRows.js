const key = value => String(value || '').trim().toLocaleLowerCase('vi').replace(/\s+/g, ' ')

export function accumulationRows(employees = [], formerEmployees = [], refunds = []) {
  const rows = new Map()
  for (const employee of employees) {
    if (!['leader', 'nhanvien'].includes(String(employee.role || '').toLowerCase())) continue
    rows.set(key(employee.employee_name), { ...employee, hasTracking: true, refunds: [] })
  }
  for (const employee of [...formerEmployees, ...refunds]) {
    const id = key(employee.employee_name)
    if (!id) continue
    if (!rows.has(id)) rows.set(id, { employee_name: employee.employee_name, employment_status: employee.employment_status, hasTracking: false, refunds: [] })
    if (employee.employment_status) rows.get(id).employment_status = employee.employment_status
  }
  for (const refund of refunds) rows.get(key(refund.employee_name))?.refunds.push(refund)
  return [...rows.values()].map(row => ({ ...row, refundedTotal: (row.periods || []).reduce((sum, period) => sum + Number(period.refund || 0), 0), configuredRefund: row.refunds.reduce((sum, item) => sum + Number(item.amount || 0), 0) }))
    .sort((a, b) => a.employee_name.localeCompare(b.employee_name, 'vi'))
}

export function filterAccumulationRows(rows, { employee = '', status = '', group = '' } = {}) {
  return rows.filter(row => {
    if (employee && row.employee_name !== employee) return false
    if (status && (row.employment_status || 'Chưa có trạng thái') !== status) return false
    if (group === 'completed') return row.hasTracking && (row.completed || Number(row.remaining || 0) <= 0)
    if (group === 'active') return row.hasTracking && !row.completed && Number(row.remaining || 0) > 0
    // A configured refund is not proof of payment: use saved payroll periods.
    if (group === 'refunded') return (row.periods || []).some(period => Number(period.refund || 0) > 0)
    return true
  })
}
