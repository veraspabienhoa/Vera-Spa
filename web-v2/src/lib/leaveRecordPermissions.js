const normalizeReason = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()

export const LETAN_REASON_GROUPS = [
  ['Nghỉ CÓ phép', 'Đi trễ CÓ phép', 'Về sớm CÓ phép'],
  ['Nghỉ KHÔNG phép', 'Đi trễ KHÔNG phép', 'Về sớm KHÔNG phép'],
  ['Nghỉ CUỐI TUẦN CÓ phép', 'Đi trễ CUỐI TUẦN CÓ phép', 'Về sớm CUỐI TUẦN CÓ phép'],
  ['Nghỉ CUỐI TUẦN KHÔNG phép', 'Đi trễ CUỐI TUẦN KHÔNG phép', 'Về sớm CUỐI TUẦN KHÔNG phép'],
  ['Leader nghỉ phép theo chính sách', 'Leader đi trễ sớm theo chính sách', 'Leader về sớm về sớm theo chính sách'],
]

const EDITOR_ROLES = new Set(['letan', 'quanly'])
export const EMPLOYEE_SELF_SERVICE_ROLES = new Set(['nhanvien', 'leader', 'locker', 'tapvu'])
export function letanReasonGroup(reason, groups = LETAN_REASON_GROUPS) {
  const key = normalizeReason(reason)
  const matched = groups.find((reasons) => reasons.some((item) => normalizeReason(item) === key))
  if (matched) return matched
  if (key === normalizeReason('Leader về sớm theo chính sách')) {
    return groups.find((reasons) => reasons.some((item) => normalizeReason(item) === normalizeReason('Leader về sớm về sớm theo chính sách'))) || null
  }
  return null
}

export function letanReasonChoices(role, recordDate, currentReason, today, letanLeavePolicy) {
  const roleKey = String(role || '').trim().toLowerCase()
  if (!EDITOR_ROLES.has(roleKey) || recordDate !== today || letanLeavePolicy?.enabled === false) return null
  const groups = letanLeavePolicy?.groups?.map((group) => group.reasons) || LETAN_REASON_GROUPS
  return letanReasonGroup(currentReason, groups)
}

const employeeNoticeDays = (leaveType, policy = {}) => (
  normalizeReason(leaveType).includes('khong phep')
    ? Number(policy.unpaid_notice_days ?? 1)
    : Number(policy.regular_notice_days ?? 3)
)

const addIsoDays = (value, days) => {
  const [year, month, day] = String(value || '').split('-').map(Number)
  if (!year || !month || !day) return ''
  return new Date(Date.UTC(year, month - 1, day + days)).toISOString().slice(0, 10)
}

const employeeDateAllowed = (recordDate, leaveType, today, policy) => (
  Boolean(recordDate && today) && recordDate >= today && recordDate >= addIsoDays(today, employeeNoticeDays(leaveType, policy))
)

export function canEditLeaveRecord({ role, allowedByPermission, recordDate, currentReason, currentLeaveType, today, isOwnRecord, employeeSelfServicePolicy, letanLeavePolicy }) {
  const roleKey = String(role || '').trim().toLowerCase()
  if (roleKey === 'admin') return true
  if (EMPLOYEE_SELF_SERVICE_ROLES.has(roleKey)) {
    if (employeeSelfServicePolicy?.enabled !== false) {
      // The server checks both old and new types. A future paid row can
      // still change to Không phép at the shorter notice boundary.
      return Boolean(isOwnRecord) && (employeeDateAllowed(recordDate, currentLeaveType, today, employeeSelfServicePolicy)
        || employeeDateAllowed(recordDate, 'Không phép', today, employeeSelfServicePolicy))
    }
    return Boolean(isOwnRecord) && Boolean(allowedByPermission) && Boolean(recordDate && today) && recordDate >= today
  }
  if (!EDITOR_ROLES.has(roleKey)) return Boolean(allowedByPermission)
  if (!recordDate || recordDate < today) return false
  const letanGroups = letanLeavePolicy?.groups?.map((group) => group.reasons) || LETAN_REASON_GROUPS
  if (recordDate === today && letanLeavePolicy?.enabled !== false && letanReasonGroup(currentReason, letanGroups)) return true
  return Boolean(allowedByPermission)
}

export function canDeleteLeaveRecord({ role, allowedByPermission, recordDate, currentReason, currentLeaveType, today, isOwnRecord, employeeSelfServicePolicy, letanLeavePolicy }) {
  const roleKey = String(role || '').trim().toLowerCase()
  if (roleKey === 'admin') return true
  if (EMPLOYEE_SELF_SERVICE_ROLES.has(roleKey)) {
    if (employeeSelfServicePolicy?.enabled !== false) {
      return Boolean(isOwnRecord) && employeeDateAllowed(recordDate, currentLeaveType, today, employeeSelfServicePolicy)
    }
    return Boolean(isOwnRecord) && Boolean(allowedByPermission) && Boolean(recordDate && today) && recordDate >= today
  }
  if (!EDITOR_ROLES.has(roleKey)) return Boolean(allowedByPermission)
  if (!recordDate || recordDate < today) return false
  const letanGroups = letanLeavePolicy?.groups?.map((group) => group.reasons) || LETAN_REASON_GROUPS
  if (recordDate === today && letanLeavePolicy?.enabled !== false && letanReasonGroup(currentReason, letanGroups)) return false
  return Boolean(allowedByPermission)
}

// Match the API's notice_days(policy, old_row, new_reason) before offering a
// candidate. Authorization and all catalog rules are still checked on save.
export function canChangeLeaveReason(context, nextReason) {
  if (!canEditLeaveRecord(context)) return false
  const group = letanReasonChoices(context.role, context.recordDate, context.currentReason, context.today, context.letanLeavePolicy)
  if (group && !group.some((name) => normalizeReason(name) === normalizeReason(nextReason.name))) return false
  const role = String(context.role || '').trim().toLowerCase()
  if (!EMPLOYEE_SELF_SERVICE_ROLES.has(role) || context.employeeSelfServicePolicy?.enabled === false) return true
  const leaveType = [context.currentLeaveType, nextReason.leave_type].some((value) => normalizeReason(value).includes('khong phep'))
    ? 'Không phép' : nextReason.leave_type
  return employeeDateAllowed(context.recordDate, leaveType, context.today, context.employeeSelfServicePolicy)
}
