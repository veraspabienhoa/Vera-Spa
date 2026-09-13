// UI dates are always dd/mm/yyyy; API values remain ISO. Business time is Vietnam time.
export const ISO_DATE = /^(\d{4})-(\d{2})-(\d{2})$/
const VN_DATE = /^(\d{2})\/(\d{2})\/(\d{4})$/

export function parseVeraDate(value) {
  const match = String(value || '').trim().match(VN_DATE)
  if (!match) return ''
  const iso = `${match[3]}-${match[2]}-${match[1]}`
  const date = new Date(`${iso}T00:00:00Z`)
  return Number.isFinite(date.getTime()) && date.toISOString().slice(0, 10) === iso ? iso : ''
}

export function formatVeraDate(value, fallback = '') {
  const raw = String(value || '').trim()
  const match = raw.match(ISO_DATE)
  if (match) {
    const display = `${match[3]}/${match[2]}/${match[1]}`
    return parseVeraDate(display) ? display : fallback
  }
  const vn = raw.match(/^(\d{1,2})\/(\d{1,2})\/(\d{4})$/)
  if (vn) {
    const display = `${vn[1].padStart(2, '0')}/${vn[2].padStart(2, '0')}/${vn[3]}`
    return parseVeraDate(display) ? display : fallback
  }
  return fallback
}

const vietnamDateTime = new Intl.DateTimeFormat('en-GB', {
  timeZone: 'Asia/Ho_Chi_Minh', day: '2-digit', month: '2-digit', year: 'numeric',
  hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23',
})
export function formatVeraDateTime(value, fallback = '—') {
  const day = formatVeraDate(value)
  if (day) return day
  if (!value) return fallback
  // Do not guess ambiguous slash dates; timestamps without an offset are Vietnam local time.
  let raw = value
  if (typeof raw === 'string') {
    const vn = raw.trim().match(/^(\d{1,2}\/\d{1,2}\/\d{4})[ ,T]+(\d{2}:\d{2}(?::\d{2})?)$/)
    if (vn) {
      const display = formatVeraDate(vn[1])
      if (!display) return fallback
      raw = `${parseVeraDate(display)}T${vn[2]}+07:00`
    }
    if (!/^\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}/.test(raw)) return fallback
    if (!formatVeraDate(raw.slice(0, 10))) return fallback
    raw = raw.replace(' ', 'T')
    if (!/(?:Z|[+-]\d{2}:?\d{2})$/i.test(raw)) raw += '+07:00'
  }
  const date = new Date(raw)
  if (!Number.isFinite(date.getTime())) return fallback
  const p = Object.fromEntries(vietnamDateTime.formatToParts(date).map(part => [part.type, part.value]))
  return `${p.day}/${p.month}/${p.year} ${p.hour}:${p.minute}:${p.second}`
}
