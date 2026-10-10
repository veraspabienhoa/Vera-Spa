import { ISO_DATE, formatVeraDate } from './veraDate.js'

export const evaluationCriteria = [['craft_score','Tay nghề'],['communication_score','Giao tiếp'],['attitude_score','Thái độ'],['discipline_score','Kỷ luật'],['appearance_score','Ngoại hình'],['hygiene_score','Vệ sinh'],['attendance_score','Chuyên cần']]
export const trainingIdentityKey = user => JSON.stringify([user?.id, user?.employee_username, user?.username, user?.email, user?.role, user?.permissions])

const validDay = value => ISO_DATE.test(String(value || '')) && Boolean(formatVeraDate(value))

export function trainingDateRange({ mode, day, month, start, end }) {
  if (mode === 'all') return {}
  if (mode === 'day') return validDay(day) ? { date_from: day, date_to: day } : null
  if (mode === 'month') {
    if (!/^\d{4}-\d{2}$/.test(month || '') || !validDay(`${month}-01`)) return null
    const [year, m] = month.split('-').map(Number)
    const last = new Date(Date.UTC(year, m, 0)).getUTCDate()
    return { date_from: `${month}-01`, date_to: `${month}-${String(last).padStart(2, '0')}` }
  }
  return mode === 'custom' && validDay(start) && validDay(end) && start <= end ? { date_from: start, date_to: end } : null
}

export function trainingRangeLabel(filters) {
  return filters?.date_from ? `${formatVeraDate(filters.date_from)} đến ${formatVeraDate(filters.date_to)}` : 'Tất cả thời gian'
}

export function validTrainingScore(value, max = 5) {
  return typeof value !== 'boolean' && value != null && value !== '' && Number.isFinite(Number(value)) && Number(value) >= 1 && Number(value) <= max
}

export async function readCompleteTrainingReport(load, employee, filters, signal) {
  const query = { ...filters, page_size: 100 }
  const report = await load(employee, query, { signal })
  signal.throwIfAborted()
  const history = [...(report.history || [])]
  // Each page includes the complete chart/journal DTO. Reject same-count edits
  // as well as inserts/deletes instead of combining multiple report snapshots.
  const signature = value => JSON.stringify([value.employee_username, value.progress, value.evaluation_details, value.evaluations, value.latest_radar])
  const initialSignature = signature(report)
  const total = Number(report.history_total)
  if (!Number.isInteger(total) || total < history.length || total > 100000) throw new Error('Báo cáo quá lớn hoặc dữ liệu chưa ổn định. Hãy thu hẹp khoảng ngày và thử lại.')
  for (let page = 2; history.length < total; page++) {
    signal.throwIfAborted()
    const next = await load(employee, { ...query, page }, { signal })
    signal.throwIfAborted()
    if (Number(next.history_total) !== total || signature(next) !== initialSignature || !next.history?.length) throw new Error('Dữ liệu đã thay đổi trong lúc tải. Hãy mở lại báo cáo.')
    history.push(...next.history)
  }
  if (history.length !== total || new Set(history.map(item => `${item.type}:${item.id}`)).size !== total) throw new Error('Dữ liệu đã thay đổi trong lúc tải. Hãy mở lại báo cáo.')
  return { ...report, history }
}

// This basename rule mirrors the server and preserves Vietnamese display names.
export function trainingReportFilename(name, format) {
  const safe = Array.from(String(name || 'NhanVien').normalize('NFC')).map(char => {
    const code = char.codePointAt(0)
    return code < 32 || (code >= 127 && code <= 159) || /[<>:"/\\|?*]/.test(char) ? '_' : char
  }).join('').replace(/\s+/g, ' ').replace(/^[ .]+|[ .]+$/g, '')
  let cleaned = '', bytes = 0
  const encoder = new TextEncoder()
  for (const char of safe) {
    bytes += encoder.encode(char).length
    if (bytes > 200) break
    cleaned += char
  }
  return `${cleaned.replace(/[ .]+$/g, '') || 'NhanVien'}_VERA_DaoTao.${format}`
}

export function trainingReportResponseFilename(header, format) {
  const encoded = /filename\*=UTF-8''([^;]+)/i.exec(header || '')?.[1]
  if (!encoded) return null
  try {
    const name = decodeURIComponent(encoded)
    // Only use the expected, sanitized server basename; malformed or unrelated
    // headers fall back to the selected employee's display name at the caller.
    const suffix = `_VERA_DaoTao.${format}`
    return name.endsWith(suffix) && trainingReportFilename(name.slice(0, -suffix.length), format) === name ? name : null
  } catch { return null }
}
