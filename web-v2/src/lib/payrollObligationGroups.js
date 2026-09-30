const employeeKey = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').replace(/Đ/g, 'D').trim().toLowerCase().replace(/\s+/g, ' ')
const signature = item => JSON.stringify([employeeKey(item.employee_name), item.type || 'Tạm hoãn vi phạm', Number(item.amount || 0), item.period_start || '', item.period_end || '', item.due_from || '', String(item.content || 'Chưa hoàn thành nghĩa vụ Vi phạm').trim()])

// Groups include both legacy and Web V2 claims; obligations contains the same
// Web V2 claims (with deletion IDs), plus manual claims without a type.
export function combineObligationGroups(groups = [], obligations = []) {
  const details = groups.filter(group => ['Âm thực nhận', 'Tạm hoãn vi phạm'].includes(group.type))
    .flatMap(group => (group.details || []).map(item => ({ ...item, type: item.type || group.type })))
  const unmatched = new Set(details.map((_, index) => index))
  for (const item of obligations) {
    const index = details.findIndex((detail, i) => unmatched.has(i) && signature(detail) === signature(item))
    if (index >= 0) {
      details[index] = { ...details[index], id: item.id }
      unmatched.delete(index)
    } else details.push({ ...item, type: item.type || 'Tạm hoãn vi phạm' })
  }
  const employees = new Map()
  for (const item of details) {
    const key = employeeKey(item.employee_name), amount = Number(item.amount || 0)
    if (!key || amount <= 0) continue
    if (item.status && employeeKey(item.status) !== 'chua hoan thanh') continue
    if (!employees.has(key)) employees.set(key, { key, employee_name: item.employee_name, negative: 0, deferred: 0, details: [] })
    const row = employees.get(key)
    row[item.type === 'Âm thực nhận' ? 'negative' : 'deferred'] += amount
    row.details.push(item)
  }
  return [...employees.values()].map(row => ({ ...row, total: row.negative + row.deferred }))
    .sort((a, b) => b.total - a.total || a.employee_name.localeCompare(b.employee_name, 'vi'))
}
