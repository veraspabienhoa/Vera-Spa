const ANNUAL = 'Nghỉ Phép năm'
const LONG = 'Nghỉ làm đẹp'
const RESIGNATION = 'Nghỉ việc'

export const APPROVED_LEAVE_FILTERS = [
  { id: 'all', label: 'Tất cả' },
  { id: 'annual', label: 'Phép năm' },
  { id: 'long', label: 'Nghỉ làm đẹp' },
  { id: 'active', label: 'Đang nghỉ' },
  { id: 'waiting', label: 'Chờ nghỉ' },
  { id: 'completed', label: 'Đã kết thúc kỳ nghỉ' },
  { id: 'resignation', label: 'Nghỉ việc' },
]

export function vietnamToday(value = new Date()) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(value)
  const part = (type) => parts.find((item) => item.type === type)?.value || ''
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function approvedLeaveStatus(item, today = vietnamToday()) {
  if (item?.source === 'resignation' || item?.request_type === RESIGNATION) {
    return { id: 'resignation', label: RESIGNATION }
  }
  if (item?.leave_completed || (item?.end_date && item.end_date < today)) {
    return { id: 'completed', label: 'Đã kết thúc kỳ nghỉ' }
  }
  if (item?.start_date && item.start_date > today) {
    return { id: 'waiting', label: 'Chờ nghỉ' }
  }
  if (item?.start_date && item.start_date <= today && (!item.end_date || item.end_date >= today)) {
    return { id: 'active', label: 'Đang nghỉ' }
  }
  return { id: 'unknown', label: '—' }
}

function normalizeSearch(value) {
  return String(value || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '')
    .replace(/[đĐ]/g, 'd').toLocaleLowerCase('vi-VN').trim()
}

export function filterApprovedLeaveItems(approvedRequests, resignationRequests, {
  filter = 'all', search = '', today = vietnamToday(),
} = {}) {
  const items = [
    ...(Array.isArray(approvedRequests) ? approvedRequests : []).map((item) => ({ ...item, source: 'leave' })),
    ...(Array.isArray(resignationRequests) ? resignationRequests : []).map((item) => ({ ...item, source: 'resignation' })),
  ]
  const query = normalizeSearch(search)
  return items.filter((item) => {
    if (query && !normalizeSearch(item.employee_name).includes(query)) return false
    if (filter === 'annual') return item.source === 'leave' && item.request_type === ANNUAL
    if (filter === 'long') return item.source === 'leave' && item.request_type === LONG
    if (['active', 'waiting', 'completed'].includes(filter)) return approvedLeaveStatus(item, today).id === filter
    if (filter === 'resignation') return item.source === 'resignation'
    return true
  })
}
