export function trainingDailySummary(sessions = []) {
  const days = new Map()
  const minutes = value => { const [h,m] = String(value || '').split(':').map(Number); return Number.isFinite(h) && Number.isFinite(m) ? h * 60 + m : null }
  for (const session of sessions) {
    const date = String(session.training_date || '').slice(0,10)
    if (!date) continue
    const start = minutes(session.start_time), end = minutes(session.end_time)
    const duration = start !== null && end !== null && end > start ? end - start : 0
    const day = days.get(date) || { date, minutes:0, sessions:[] }
    day.minutes += duration
    day.sessions.push({ ...session, minutes:duration })
    days.set(date,day)
  }
  return [...days.values()].sort((a,b) => b.date.localeCompare(a.date))
}
