// Revision metadata belongs to a cell's server baseline, never to editable or
// copied values. In particular, an absent cell always starts at revision zero.
export function emptyScheduleCell() {
  return {
    shift_code: '', overtime_shift: '', start_time: '', end_time: '',
    overtime_start_time: '', overtime_end_time: '', note: '',
    combo_sold: false, combo_sale_date: '', combo_customer_name: '',
    combo_customer_phone: '', combo_ticket: '', combo_note: '',
  }
}

export const scheduleCellKey = (username, day) => `${username}__${day}`

export function scheduleCellValue(row = {}) {
  const value = emptyScheduleCell()
  // Blank means deletion; clipboard/import metadata cannot create an endlessly
  // dirty empty cell that has no corresponding upsert or delete operation.
  if (!row.shift_code) return value
  for (const field of Object.keys(value)) {
    value[field] = field === 'combo_sold' ? Boolean(row[field]) : String(row[field] || '')
    if (field.endsWith('_time')) value[field] = value[field].slice(0, 5)
  }
  return value
}

export const sameScheduleCell = (left, right) => JSON.stringify(scheduleCellValue(left)) === JSON.stringify(scheduleCellValue(right))

export function emptyScheduleWorkspace() {
  return { saved: {}, drafts: {}, revisions: {}, conflicts: {}, ready: false, needsRefresh: false, manualSaveRequired: false, manualSaveGeneration: 0 }
}

export function reconcileSchedule(workspace, rows, forcedConflicts = []) {
  const saved = {}, revisions = {}, conflicts = {}
  for (const row of rows) {
    if (!Number.isSafeInteger(row.revision) || row.revision < 1) throw new Error('Lịch chưa có phiên bản hợp lệ. Vui lòng tải lại trước khi sửa.')
    const key = scheduleCellKey(row.employee_username, row.work_date)
    saved[key] = scheduleCellValue(row)
    revisions[key] = row.revision
  }
  const drafts = { ...saved }
  const forced = new Set(forcedConflicts.map(row => scheduleCellKey(row.employee_username, row.work_date)))
  if (workspace.ready) {
    for (const key of new Set([...Object.keys(workspace.saved), ...Object.keys(workspace.drafts)])) {
      const local = scheduleCellValue(workspace.drafts[key])
      if (sameScheduleCell(local, workspace.saved[key]) || sameScheduleCell(local, saved[key])) continue
      drafts[key] = local
      if (workspace.conflicts[key] || forced.has(key) || (workspace.revisions[key] || 0) !== (revisions[key] || 0)) {
        conflicts[key] = true
      }
    }
  }
  return { ...workspace, saved, drafts, revisions, conflicts, ready: true, needsRefresh: false }
}

export function acknowledgeSchedule(workspace, changes, result, submittedManualGeneration = workspace.manualSaveGeneration) {
  const returned = new Map((result.revisions || []).map(row => [scheduleCellKey(row.employee_username, row.work_date), row.revision]))
  // Validate the entire acknowledgement before changing any local baseline.
  for (const { key, after } of changes) {
    if (after.shift_code && (!Number.isSafeInteger(returned.get(key)) || returned.get(key) < 1)) {
      throw new Error('Máy chủ chưa xác nhận phiên bản lịch. Cần tải lại để kiểm tra kết quả lưu.')
    }
  }
  const saved = { ...workspace.saved }, revisions = { ...workspace.revisions }
  for (const { key, after } of changes) {
    if (after.shift_code) {
      saved[key] = scheduleCellValue(after)
      revisions[key] = returned.get(key)
    } else {
      delete saved[key]
      delete revisions[key]
    }
  }
  // Never replace drafts here: the operator may have edited again while PUT ran.
  return { ...workspace, saved, revisions,
    manualSaveRequired: workspace.manualSaveGeneration !== submittedManualGeneration && workspace.manualSaveRequired }
}

export function resolveScheduleConflict(workspace, key, useLocal) {
  const conflicts = { ...workspace.conflicts }
  delete conflicts[key]
  return { ...workspace, conflicts, manualSaveRequired: true, manualSaveGeneration: workspace.manualSaveGeneration + 1,
    drafts: useLocal ? workspace.drafts : { ...workspace.drafts, [key]: scheduleCellValue(workspace.saved[key]) } }
}

export function scheduleHasChanges(workspace) {
  return [...new Set([...Object.keys(workspace.saved), ...Object.keys(workspace.drafts)])]
    .some(key => !sameScheduleCell(workspace.saved[key], workspace.drafts[key]))
}
