// Share only requests that are currently in flight. No response or identity cache.
const pending = new Map()
const cancelled = () => Object.assign(new Error('Đã dừng tải dữ liệu.'), { name: 'AbortError' })
export function invalidateSharedReads() { pending.clear() }

export function sharedRead(key, load, signal) {
  if (signal?.aborted) return Promise.reject(cancelled())
  let entry = pending.get(key)
  if (!entry) {
    const controller = new AbortController()
    entry = { controller, readers: 0, settled: false }
    entry.promise = Promise.resolve().then(() => load(controller.signal))
    const finish = () => { entry.settled = true; if (pending.get(key) === entry) pending.delete(key) }
    entry.promise.then(finish, finish)
    // Bound simultaneous keys without cancelling an existing reader.
    if (pending.size >= 128) pending.delete(pending.keys().next().value)
    pending.set(key, entry)
  }
  entry.readers += 1
  return new Promise((resolve, reject) => {
    let done = false
    const finish = (callback, value) => {
      if (done) return
      done = true; signal?.removeEventListener('abort', abort)
      entry.readers -= 1
      if (!entry.readers && !entry.settled) {
        if (pending.get(key) === entry) pending.delete(key)
        entry.controller.abort()
      }
      callback(value)
    }
    const abort = () => finish(reject, cancelled())
    signal?.addEventListener('abort', abort, { once: true })
    entry.promise.then(value => finish(resolve, value), error => finish(reject, error))
  })
}
