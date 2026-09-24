// Completion-based polling: at most one pending request per poller, no hidden-tab traffic.
export function createVisiblePoller(load, { interval, document: doc = document, setTimeout: later = setTimeout, clearTimeout: cancel = clearTimeout } = {}) {
  let stopped = false, inFlight = false, timer = null
  const clear = () => { if (timer !== null) cancel(timer); timer = null }
  const refresh = async () => {
    if (stopped || inFlight || doc.hidden) return
    clear(); inFlight = true
    try { await load() } catch { /* Next visible poll may recover. */ }
    finally {
      inFlight = false
      if (!stopped && !doc.hidden) timer = later(refresh, interval)
    }
  }
  const visibility = () => { clear(); if (!doc.hidden) void refresh() }
  doc.addEventListener('visibilitychange', visibility)
  void refresh()
  return { refresh, stop() { stopped = true; clear(); doc.removeEventListener('visibilitychange', visibility) } }
}
