// Recompute source earnings while keeping explicit edits in the same payroll period.
export function preservePayrollEdits(result, previous, fields, recalculate) {
  const samePeriod = previous?.start === result.start && previous?.end === result.end
  const saved = new Map((samePeriod ? previous.rows || [] : []).map(row => [row['Tên Hệ thống'], row]))
  return { ...result, rows: (result.rows || []).map(row => {
    const old = saved.get(row['Tên Hệ thống'])
    // Legacy snapshots predate edit metadata: keep their editable values intact.
    const overrides = old ? old.__manual_overrides ?? Object.fromEntries(fields.filter(field => field in old).map(field => [field, old[field]])) : {}
    const valid = Object.fromEntries(fields.filter(field => Object.hasOwn(overrides, field)).map(field => [field, Number(overrides[field] || 0)]))
    return recalculate({ ...row, ...valid, __manual_overrides: valid })
  }) }
}
