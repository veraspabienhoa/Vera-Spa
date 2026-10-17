export const normalizeLeaveFilter = value => String(value || '').normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '').replace(/[đĐ]/g, 'd').toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ').trim()

export const matchesLeaveDetails = (row, filters = {}) => ['leave_reason', 'leave_type', 'detail']
  .every(key => normalizeLeaveFilter(row[key]).includes(normalizeLeaveFilter(filters[key])))
