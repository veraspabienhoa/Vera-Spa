import { veraApi } from './api'
import { createVisiblePoller } from './visiblePoller'

// Inbox and popup share one visible-tab request. The last subscriber owns
// cleanup so cached notifications cannot cross a sign-out/sign-in boundary.
export function createNotificationFeed(load, makePoller = createVisiblePoller) {
  const listeners = new Set()
  let poller = null, cached = null, generation = 0
  return {
    subscribe(listener) {
      listeners.add(listener)
      if (cached) listener(cached)
      if (!poller) {
        const current = generation
        poller = makePoller(async () => {
          const result = await load()
          if (current !== generation) return
          cached = result
          for (const receive of listeners) receive(result)
        }, { interval: 60000 })
      }
      return () => {
        listeners.delete(listener)
        if (!listeners.size) {
          generation += 1
          poller?.stop()
          poller = null
          cached = null
        }
      }
    },
    refresh() { return poller?.refresh() },
  }
}

const feed = createNotificationFeed(() => veraApi.notificationFeed())
export const subscribeNotificationFeed = listener => feed.subscribe(listener)
export const refreshNotificationFeed = () => feed.refresh()
