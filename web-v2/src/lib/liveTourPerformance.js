// Live Tour only displays minute-granularity countdowns. Updating the entire
// workspace every second needlessly rebuilds the room grid, employee table and
// financial panels. Twenty seconds preserves that display granularity while
// reducing clock-driven React renders by exactly 20x.
export const LIVE_TOUR_CLOCK_TICK_MS = 20_000
export const LIVE_TOUR_POLL_MS = 3_000

export function startLiveTourClock(setClock, windowObject = window) {
  return windowObject.setInterval(() => setClock(Date.now()), LIVE_TOUR_CLOCK_TICK_MS)
}

export function startLiveTourPolling(poll, windowObject = window, documentObject = document) {
  return windowObject.setInterval(() => {
    // A hidden tab cannot help an operator and used to keep occupying API/DB
    // capacity. The visibility event performs an immediate catch-up instead.
    if (documentObject.visibilityState !== 'hidden') poll()
  }, LIVE_TOUR_POLL_MS)
}
