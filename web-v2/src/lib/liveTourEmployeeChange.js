export function canChangeEmployee(record, now = Date.now()) {
  const start = Date.parse(record?._employee_change_started_at || '')
  const until = Date.parse(record?._employee_change_until || '')
  return record?._tour_groups?.includes('doing') === true && Number.isFinite(start) && Number.isFinite(until)
    && now >= start && now <= until && until > start
}
