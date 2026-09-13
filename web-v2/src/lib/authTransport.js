// Bound both the request and response-body read. Do not apply this short deadline
// to payroll/export requests, which have different runtime budgets.
export async function authJsonRequest(url, options = {}) {
  const controller = new AbortController()
  const abort = () => controller.abort()
  const callerSignal = options.signal
  if (callerSignal?.aborted) abort()
  else callerSignal?.addEventListener('abort', abort, { once: true })
  let timedOut = false
  const timer = setTimeout(() => { timedOut = true; abort() }, 15000)
  try {
    const response = await fetch(url, { ...options, signal: controller.signal })
    let payload
    try { payload = await response.json() } catch (error) {
      if (controller.signal.aborted) throw error
      if (response.ok) {
        throw Object.assign(new Error('Máy chủ VERA trả dữ liệu xác thực không hợp lệ. Vui lòng thử lại.'), { status: 502 })
      }
      // A proxy can return HTML on an error. Preserve its HTTP status without
      // displaying the HTML or confusing a temporary 5xx with rejected tokens.
      payload = {}
    }
    return { response, payload }
  } catch (error) {
    if (timedOut) {
      throw Object.assign(new Error('Máy chủ VERA phản hồi quá chậm. Vui lòng thử xác minh lại.'), { code: 'VERA_API_TIMEOUT' })
    }
    throw error
  } finally {
    clearTimeout(timer)
    callerSignal?.removeEventListener('abort', abort)
  }
}
