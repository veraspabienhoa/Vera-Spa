export const QUARTER_HOUR_MS = 15 * 60 * 1000

export function nextQuarterHourAt(now) {
  return (Math.floor(now / QUARTER_HOUR_MS) + 1) * QUARTER_HOUR_MS
}

// Align reminders to :00, :15, :30, and :45 instead of counting from mount time.
export function startQuarterHourBookingReminder({
  load,
  onReminder,
  now = () => Date.now(),
  setTimer = window.setTimeout,
  clearTimer = window.clearTimeout,
}) {
  let timer
  let stopped = false

  const schedule = () => {
    const scheduledAt = nextQuarterHourAt(now())
    timer = setTimer(async () => {
      if (stopped) return
      try {
        const result = await load()
        if (!stopped && Number(result?.total) > 0) onReminder(result)
      } catch {
        // A later quarter-hour check retries without interrupting Live Tour.
      }
      if (!stopped) schedule()
    }, Math.max(0, scheduledAt - now()))
  }

  schedule()
  return () => {
    stopped = true
    clearTimer(timer)
  }
}
