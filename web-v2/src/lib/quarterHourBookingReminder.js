export const QUARTER_HOUR_MS = 15 * 60 * 1000

export function nextQuarterHourAt(now) {
  return (Math.floor(now / QUARTER_HOUR_MS) + 1) * QUARTER_HOUR_MS
}

// Keep the quarter-hour schedule without background-tab reads. A tab that
// missed one or more boundaries catches up once when visible, never in a burst.
export function startQuarterHourBookingReminder({
  load,
  onReminder,
  now = () => Date.now(),
  setTimer = window.setTimeout,
  clearTimer = window.clearTimeout,
  document: doc = globalThis.document,
}) {
  let timer = null
  let stopped = false
  let inFlight = false
  let visibilityGeneration = 0
  let dueAt = nextQuarterHourAt(now())
  const hidden = () => Boolean(doc?.hidden)
  const clear = () => { if (timer !== null) clearTimer(timer); timer = null }

  const schedule = () => {
    clear()
    if (!stopped && !inFlight && !hidden()) timer = setTimer(check, Math.max(0, dueAt - now()))
  }
  const check = async () => {
    clear()
    if (stopped || inFlight || hidden()) return
    inFlight = true
    const generation = visibilityGeneration
    try {
      const result = await load()
      if (!stopped && !hidden() && generation === visibilityGeneration && Number(result?.total) > 0) onReminder(result)
    } catch {
      // A later quarter-hour check retries without interrupting Live Tour.
    } finally {
      inFlight = false
      // If hidden during a slow request, re-read on return instead of displaying
      // an old reminder or silently consuming the missed visible check.
      if (!hidden() && generation === visibilityGeneration) dueAt = nextQuarterHourAt(now())
      schedule()
    }
  }
  const visibility = () => {
    if (hidden()) visibilityGeneration += 1
    clear()
    if (!stopped && !hidden()) {
      if (now() >= dueAt) void check()
      else schedule()
    }
  }

  doc?.addEventListener('visibilitychange', visibility)
  schedule()
  return () => {
    stopped = true
    clear()
    doc?.removeEventListener('visibilitychange', visibility)
  }
}
