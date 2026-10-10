// One read at a time for a fixed panel/query. Board revisions invalidate the
// result without cancelling useful in-flight work; a burst queues one catch-up.
export function createLiveTourRefresh({ read, getRevision, onData, onError, onLoading = () => {}, delayMs = 180 }) {
  let disposed = false
  let pending = false
  let queued = false
  let timer = null
  let controller = null
  let lastLoadedRevision = null

  const isCurrent = () => lastLoadedRevision != null && (
    lastLoadedRevision === getRevision()
    || (typeof lastLoadedRevision === 'number' && typeof getRevision() === 'number' && lastLoadedRevision >= getRevision())
  )

  const schedule = () => {
    if (disposed || isCurrent()) return
    queued = true
    if (pending || timer != null) return
    onLoading(true)
    timer = setTimeout(load, delayMs)
  }

  const load = async () => {
    timer = null
    if (disposed) return
    queued = false
    pending = true
    controller = new AbortController()
    const requestRevision = getRevision()
    try {
      const value = await read({ signal: controller.signal, requestRevision })
      if (disposed) return
      // A response may have read a later snapshot than the board had when the
      // request started. Never label it with a revision observed at completion.
      lastLoadedRevision = value.revision ?? requestRevision
      onData(value, { requestRevision, loadedRevision: lastLoadedRevision })
    } catch (error) {
      if (!disposed) onError(error)
    } finally {
      pending = false
      controller = null
      if (!disposed) {
        // Failed reads release the slot too. Retry only an invalidation received
        // while busy, never spin on a timeout or a persistently stale response.
        if (queued && !isCurrent()) schedule()
        else { queued = false; onLoading(false) }
      }
    }
  }

  return {
    schedule,
    get lastLoadedRevision() { return lastLoadedRevision },
    dispose() {
      disposed = true
      queued = false
      clearTimeout(timer)
      controller?.abort()
    },
  }
}
