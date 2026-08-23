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

export async function loadLeaveRecords(date) {
  const rows = await rpc('vera_v2_leave_records', { p_date: date })
  return Array.isArray(rows) ? rows : []
}

export async function loadLeaveReasons() {
  const rows = await rpc('vera_v2_leave_reasons')
  return (rows || []).map((row) => row.reason).filter(Boolean)
}

export async function loadEmployees() {
  const rows = await rpc('vera_v2_employees')
  return Array.isArray(rows) ? rows : []
}
