import { supabase } from './supabase'

async function rpc(name, args = {}) {
  if (!supabase) throw new Error('Supabase chưa được cấu hình.')
  const { data, error } = await supabase.rpc(name, args)
  if (error) throw error
  return data
}

export async function loadLeaveSummary(date) {
  const rows = await rpc('vera_v2_leave_summary', { p_date: date })
  const row = Array.isArray(rows) ? rows[0] : rows
  return row || { working: 0, leave: 0, paid: 0, unpaid: 0 }
}

const normalizeSearch = (value) => String(value || '')
  .normalize('NFD')
  .replace(/[\u0300-\u036f]/g, '')
  .replace(/đ/g, 'd')
  .replace(/Đ/g, 'D')
  .toLocaleLowerCase('vi-VN')
  .replace(/\s+/g, ' ')
  .trim()
const matchesEmployeeName = (employeeName, searchValue) => {
  const needle = normalizeSearch(searchValue)
  if (!needle) return true
  const shortName = String(employeeName || '').split(/\s*[-–—]\s*/, 1)[0]
  return [employeeName, shortName].some((name) => normalizeSearch(name) === needle)
}

const leaveStatsGroup = (row) => {
  const key = normalizeSearch(`${row.leave_type || ''} ${row.leave_reason || ''}`)
  if (key.includes('phat sinh')) return 'generated'
  if (key.includes('khong phep')) return 'unpaid'
  if (key.includes('co phep') || key.includes('phep nam')) return 'paid'
  return ''
}

export async function loadLeaveDailyStats(start, end, employee = '') {
  const rows = await rpc('vera_v2_leave_daily_stats', { p_start: start, p_end: end })
  const dailyRows = Array.isArray(rows) ? rows.map((row) => ({ ...row, date: row.date || row.day })) : []
  const needle = normalizeSearch(employee)
  if (!needle) return dailyRows

  const records = await loadLeaveRecords(start, end)
  const baseByDate = new Map(dailyRows.map((row) => [row.date, row]))
  const buckets = new Map()
  records
    .filter((row) => matchesEmployeeName(row.employee_name, needle))
    .forEach((row) => {
      const date = row.leave_date
      const bucket = buckets.get(date) || { paid: 0, generated: 0, unpaid: 0, total_penalty: 0 }
      const group = leaveStatsGroup(row)
      if (group) bucket[group] += 1
      bucket.total_penalty += Number(row.penalty || 0)
      buckets.set(date, bucket)
    })

  return [...buckets.entries()].sort(([left], [right]) => left.localeCompare(right)).map(([date, bucket]) => {
    const base = baseByDate.get(date) || {}
    const paidLimit = Number(base.paid_limit || 0)
    const generatedLimit = Number(base.generated_limit || 0)
    return {
      ...base,
      date,
      weekday_label: base.weekday_label || '',
      total_leave: bucket.paid + bucket.generated + bucket.unpaid,
      ...bucket,
      paid_full: paidLimit > 0 && bucket.paid >= paidLimit,
      generated_full: generatedLimit === 0 ? bucket.generated > 0 : bucket.generated >= generatedLimit,
    }
  })
}

export async function loadLeaveRecords(start, end = start) {
  const dates = []
  const cursor = new Date(`${start}T00:00:00`)
  const finish = new Date(`${end}T00:00:00`)
  while (cursor <= finish && dates.length < 366) {
    const year = cursor.getFullYear()
    const month = `${cursor.getMonth() + 1}`.padStart(2, '0')
    const day = `${cursor.getDate()}`.padStart(2, '0')
    dates.push(`${year}-${month}-${day}`)
    cursor.setDate(cursor.getDate() + 1)
  }
  const batches = await Promise.all(dates.map(async (date) => {
    const rows = await rpc('vera_v2_leave_records', { p_date: date })
    return (Array.isArray(rows) ? rows : []).map((row) => ({ ...row, leave_date: row.leave_date || date }))
  }))
  return batches.flat()
}

export async function loadLeaveReasons(_date) {
  const rows = await rpc('vera_v2_leave_reasons')
  return (rows || []).map((row) => row.reason).filter(Boolean)
}

export async function loadEmployees() {
  const rows = await rpc('vera_v2_employees')
  return Array.isArray(rows) ? rows : []
}
