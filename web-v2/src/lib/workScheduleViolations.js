import { useEffect, useState } from 'react'
import { veraApi } from './api'

export function vietnamToday() {
  const parts = new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date())
  const part = key => parts.find(item => item.type === key).value
  return `${part('year')}-${part('month')}-${part('day')}`
}

export function violationMonthRange(month) {
  const [year, value] = month.split('-').map(Number)
  return { start: `${month}-01`, end: `${month}-${new Date(year, value, 0).getDate()}` }
}

export function isViolation(record) {
  return String(record.leave_type || '').normalize('NFD').replace(/[\u0300-\u036f]/g, '').toLowerCase().includes('vi pham')
}

export async function loadViolationRecords(start, end, signal) {
  if (!start || !end || end < start) throw new Error('Chọn khoảng ngày vi phạm hợp lệ.')
  const batches = []
  let month = start.slice(0, 7)
  while (month <= end.slice(0, 7)) {
    if (batches.length >= 12) throw new Error('Chỉ xem tối đa 12 tháng mỗi lần.')
    const range = violationMonthRange(month)
    batches.push({ start: start > range.start ? start : range.start, end: end < range.end ? end : range.end })
    const [year, value] = month.split('-').map(Number)
    month = value === 12 ? `${year + 1}-01` : `${year}-${String(value + 1).padStart(2, '0')}`
  }
  const records = []
  for (const range of batches) {
    const result = await veraApi.leaveRecords(range.start, range.end, { signal })
    records.push(...(result.records || []).filter(isViolation))
  }
  return records
}

export function useViolationRecords(start, end, revision = 0) {
  const [state, setState] = useState({ records: [], loading: true, error: '' })
  useEffect(() => {
    const controller = new AbortController()
    setState({ records: [], loading: true, error: '' })
    loadViolationRecords(start, end, controller.signal).then(records => {
      if (!controller.signal.aborted) setState({ records, loading: false, error: '' })
    }).catch(error => {
      if (!controller.signal.aborted) setState({ records: [], loading: false, error: error.message })
    })
    return () => controller.abort()
  }, [start, end, revision])
  return state
}

