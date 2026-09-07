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
  Boolean(recordDate && today) && recordDate >= addIsoDays(today, employeeNoticeDays(leaveType, policy))
)

export function canEditLeaveRecord({ role, allowedByPermission, recordDate, currentReason, currentLeaveType, today, isOwnRecord, employeeSelfServicePolicy, letanLeavePolicy }) {
  const roleKey = String(role || '').trim().toLowerCase()
  if (roleKey === 'admin') return true
  if (EMPLOYEE_SELF_SERVICE_ROLES.has(roleKey)) {
    if (employeeSelfServicePolicy?.enabled !== false) {
      return Boolean(isOwnRecord) && employeeDateAllowed(recordDate, currentLeaveType, today, employeeSelfServicePolicy)
    }
    return Boolean(isOwnRecord) && Boolean(allowedByPermission)
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
    return Boolean(isOwnRecord) && Boolean(allowedByPermission)
  }
  if (!EDITOR_ROLES.has(roleKey)) return Boolean(allowedByPermission)
  if (!recordDate || recordDate < today) return false
  const letanGroups = letanLeavePolicy?.groups?.map((group) => group.reasons) || LETAN_REASON_GROUPS
  if (recordDate === today && letanLeavePolicy?.enabled !== false && letanReasonGroup(currentReason, letanGroups)) return false
  return Boolean(allowedByPermission)
}
