const employeeKey = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toLowerCase().replace(/\s+/g, ' ')

export function combineObligationGroups(groups = []) {
  const employees = new Map()
  for (const group of groups) {
    if (!['Âm thực nhận', 'Tạm hoãn vi phạm'].includes(group.type)) continue
    for (const item of group.summary || []) {
      const key = employeeKey(item.employee_name)
      if (!key) continue
      if (!employees.has(key)) employees.set(key, { key, employee_name: item.employee_name, negative: 0, deferred: 0, details: [] })
      const row = employees.get(key)
      row[group.type === 'Âm thực nhận' ? 'negative' : 'deferred'] += Number(item.total || 0)
    }
    for (const item of group.details || []) {
      const row = employees.get(employeeKey(item.employee_name))
      if (row) row.details.push({ ...item, type: item.type || group.type })
    }
  }
  return [...employees.values()].map(row => ({ ...row, total: row.negative + row.deferred }))
    .sort((a, b) => b.total - a.total || a.employee_name.localeCompare(b.employee_name, 'vi'))
}

