import { formatVeraDate, formatVeraDateTime } from './veraDate.js'

export function vietnamToday(now = new Date()) {
  const parts = Object.fromEntries(new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Ho_Chi_Minh', year: 'numeric', month: '2-digit', day: '2-digit',
  }).formatToParts(now).map(item => [item.type, item.value]))
  return `${parts.year}-${parts.month}-${parts.day}`
}

export function holidayPayload(form, requestId) {
  return {
    request_id: requestId, scope: form.scope, mode: form.mode, note: form.note.trim(),
    departments: form.scope === 'departments' ? form.departments : [],
    employees: form.scope === 'employees' ? form.employees : [],
    dates: form.mode === 'day' ? [form.day] : form.mode === 'dates' ? form.dates : [],
    date_from: form.mode === 'range' ? form.dateFrom : null,
    date_to: form.mode === 'range' ? form.dateTo : null,
    ...(form.timeMode === 'hours' ? { time_from: form.timeFrom, time_to: form.timeTo } : {}),
    starts_at: form.mode === 'hours' ? form.startsAt : null,
    ends_at: form.mode === 'hours' ? form.endsAt : null,
  }
}

export function holidayPeriodsLabel(row) {
  return (row.periods || []).map(period => {
    if (row.mode === 'hours') return `${formatVeraDateTime(period.starts_at)} → ${formatVeraDateTime(period.ends_at)}`
    const start = vietnamToday(new Date(period.starts_at))
    const end = vietnamToday(new Date(new Date(period.ends_at).getTime() - 1))
    return start === end ? formatVeraDate(start) : `${formatVeraDate(start)} → ${formatVeraDate(end)}`
  }).join('; ')
}
