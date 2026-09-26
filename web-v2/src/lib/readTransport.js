import { sharedRead } from './sharedRead.js'
// Read-only deadline and cancellation. Financial writes never enter this path.
async function unsharedReadJsonRequest(url, options = {}, { timeoutMs = 20000, attempts = 3 } = {}) {
  const controller = new AbortController()
  const abort = () => controller.abort(options.signal?.reason)
  if (options.signal?.aborted) abort()
  else options.signal?.addEventListener('abort', abort, { once: true })
  const timer = setTimeout(() => controller.abort(), timeoutMs)
  const pause = ms => new Promise((resolve, reject) => {
    if (controller.signal.aborted) { reject(new Error('Đã dừng tải dữ liệu.')); return }
    const onAbort = () => { clearTimeout(id); reject(new Error('Đã dừng tải dữ liệu.')) }
    const id = setTimeout(() => { controller.signal.removeEventListener('abort', onAbort); resolve() }, ms)
    controller.signal.addEventListener('abort', onAbort, { once: true })
  })
  try {
    for (let attempt = 1; attempt <= attempts; attempt += 1) {
      try {
        if (controller.signal.aborted) throw new Error('Đã dừng tải dữ liệu.')
        const response = await fetch(url, { ...options, signal: controller.signal })
        let payload
        try { payload = await response.json() } catch (error) {
          if (controller.signal.aborted) throw error
          payload = {}
        }
        return { response, payload }
      } catch (error) {
        if (controller.signal.aborted) {
          const cancelled = new Error(options.signal?.aborted ? 'Đã dừng tải dữ liệu.' : 'Máy chủ phản hồi quá lâu. Vui lòng thử tải lại.')
          cancelled.name = options.signal?.aborted ? 'AbortError' : 'TimeoutError'
          throw cancelled
        }
        if (attempt === attempts) throw error
        await pause(attempt * 600)
      }
    }
  } finally {
    clearTimeout(timer)
    options.signal?.removeEventListener('abort', abort)
  }
}

export async function readJsonRequest(url, options = {}, policy = {}) {
  if (String(options.method || 'GET').toUpperCase() !== 'GET') return unsharedReadJsonRequest(url, options, policy)
  const headers = [...new Headers(options.headers || {}).entries()].sort(([a], [b]) => a.localeCompare(b))
  const key = JSON.stringify([String(url), headers, options.credentials, options.cache, options.mode, policy.timeoutMs, policy.attempts])
  const result = await sharedRead(key, signal => unsharedReadJsonRequest(url, { ...options, signal }, policy), options.signal)
  // Callers may normalize their own rows; one panel must not mutate another's result.
  return { response: result.response, payload: structuredClone(result.payload) }
}
