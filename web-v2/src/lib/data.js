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

export async function loadLeaveDailyStats(start, end) {
  const rows = await rpc('vera_v2_leave_daily_stats', { p_start: start, p_end: end })
  return Array.isArray(rows) ? rows.map((row) => ({ ...row, date: row.date || row.day })) : []
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
