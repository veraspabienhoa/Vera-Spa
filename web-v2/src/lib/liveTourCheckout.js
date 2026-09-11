export const money = (value) => Number(value || 0).toLocaleString('vi-VN') + ' đ'

export function tipCardLabel(card) {
  const name = String(card.name || '').trim()
  const amountOnly = /^[\d\s.,]+(?:đ|₫|vnd)?$/i.test(name)
    && Number(name.replace(/\D/g, '')) === Number(card.amount)
  return !name || amountOnly ? money(card.amount) : `${name} · ${money(card.amount)}`
}

export function defaultTipMode(key) {
  try { return window.localStorage.getItem(key) === 'cards' ? 'cards' : 'manual' } catch { return 'manual' }
}

export function bookingDateTime(value = Date.now()) {
  const date = new Date(value)
  if (!Number.isFinite(date.getTime())) return { date: '', time: '' }
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', { timeZone: 'Asia/Ho_Chi_Minh',
    year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hourCycle: 'h23',
  }).formatToParts(date).map((part) => [part.type, part.value]))
  return { date: `${parts.year}-${parts.month}-${parts.day}`, time: `${parts.hour}:${parts.minute}` }
}

export function bookingTimeLabel(value) {
  const { date, time } = bookingDateTime(value || NaN)
  return date ? `${time} ${date.split('-').reverse().join('/')}` : '—'
}
