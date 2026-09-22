// UI hint only: the API independently enforces current server time and grants.
export function canStartOutsideShift(isAdmin, granted, nowMs) {
  if (isAdmin) return true
  if (granted !== true || !Number.isFinite(nowMs)) return false
  const hour = Number(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh', hour: '2-digit', hourCycle: 'h23',
  }).format(new Date(nowMs)))
  return hour >= 0 && hour < 2
}
