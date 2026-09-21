export function summarizeEmployeeRevenue(rows = []) {
  const grouped = new Map()
  for (const row of rows || []) {
    const employee = String(row?.employee_name || '').trim() || 'Chưa xác định'
    const total = Number(row?.total || 0)
    const tip = Number(row?.tip || 0)
    const service = (Number.isFinite(total) ? total : 0) - (Number.isFinite(tip) ? tip : 0)
    const current = grouped.get(employee) || { employee, service: 0, tip: 0, total: 0, tourRows: 0, requestRows: 0, rows: 0 }
    current.service += service
    current.tip += Number.isFinite(tip) ? tip : 0
    current.total += Number.isFinite(total) ? total : 0
    if (String(row?.request || '').trim().toLocaleLowerCase('vi') === 'yc') current.requestRows += 1
    else current.tourRows += 1
    current.rows += 1
    grouped.set(employee, current)
  }
  return [...grouped.values()]
    .map(item => ({
      ...item,
      service: Math.round(item.service * 100) / 100,
      tip: Math.round(item.tip * 100) / 100,
      total: Math.round(item.total * 100) / 100,
    }))
    .sort((left, right) => right.service - left.service || right.tip - left.tip || left.employee.localeCompare(right.employee, 'vi'))
}
