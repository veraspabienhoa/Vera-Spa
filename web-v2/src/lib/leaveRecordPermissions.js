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

const GROUP_BY_REASON = new Map(
  LETAN_REASON_GROUPS.flatMap((reasons, index) => reasons.map((reason) => [normalizeReason(reason), index])),
)
GROUP_BY_REASON.set(normalizeReason('Leader về sớm theo chính sách'), 4)

export function letanReasonGroup(reason) {
  const index = GROUP_BY_REASON.get(normalizeReason(reason))
  return Number.isInteger(index) ? LETAN_REASON_GROUPS[index] : null
}

export function letanReasonChoices(role, recordDate, currentReason, today) {
  if (String(role || '').trim().toLowerCase() !== 'letan' || recordDate !== today) return null
  return letanReasonGroup(currentReason)
}

export function canEditLeaveRecord({ role, allowedByPermission, recordDate, currentReason, today }) {
  const roleKey = String(role || '').trim().toLowerCase()
  if (roleKey === 'admin') return true
  if (roleKey !== 'letan') return Boolean(allowedByPermission)
  if (!recordDate || recordDate < today) return false
  if (recordDate === today && letanReasonGroup(currentReason)) return true
  return Boolean(allowedByPermission)
}

export function canDeleteLeaveRecord({ role, allowedByPermission, recordDate, currentReason, today }) {
  const roleKey = String(role || '').trim().toLowerCase()
  if (roleKey === 'admin') return true
  if (roleKey !== 'letan') return Boolean(allowedByPermission)
  if (!recordDate || recordDate < today) return false
  if (recordDate === today && letanReasonGroup(currentReason)) return false
  return Boolean(allowedByPermission)
}
