const normalize = value => String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').replace(/đ/g, 'd').toLowerCase()
const vietnamClock = new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23' })

export function isBeforeShiftReady(record, settings, clockMs) {
  const parts = Object.fromEntries(vietnamClock.formatToParts(new Date(clockMs)).map(part => [part.type, part.value]))
  const today = `${parts.year}-${parts.month}-${parts.day}`
  if (record._shift_checkin_date !== today || !record['Vào ca'] || (record._tour_groups || []).includes('leave')) return false
  const reason = normalize(record._daily_support_reason)
  const key = /ho tro ca\s*2\b/.test(reason) ? 'support2' : /ho tro ca\s*1\b/.test(reason) ? 'support1' : normalize(record['Vào ca']) === 'ca 2' ? 'shift2' : ''
  if (!key) return false
  const cutoff = settings?.[key] || { shift2: '13:00', support1: '12:00', support2: '14:00' }[key]
  return `${parts.hour}:${parts.minute}` < cutoff
}
