const apiBase = import.meta.env.VITE_VERA_API_BASE_URL?.replace(/\/$/, '') || ''
const DEVICE_KEY = 'vera-v2-device-id'
const CLAIM_PENDING_KEY = 'vera-device-claim-pending'
let installed = false

function makeDeviceId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID()
  const random = Math.random().toString(36).slice(2)
  return `vera-${Date.now().toString(36)}-${random}`
}

export function getDeviceId() {
  let value = window.localStorage.getItem(DEVICE_KEY) || ''
  if (!value) {
    value = makeDeviceId()
    window.localStorage.setItem(DEVICE_KEY, value)
  }
  return value
}

export function markFreshLoginClaim() {
  window.sessionStorage.setItem(CLAIM_PENDING_KEY, '1')
}

export function clearFreshLoginClaim() {
  window.sessionStorage.removeItem(CLAIM_PENDING_KEY)
}

export function hasFreshLoginClaim() {
  return window.sessionStorage.getItem(CLAIM_PENDING_KEY) === '1'
}

function apiUrlWithDevice(input) {
  if (!apiBase) return null
  const raw = input instanceof Request ? input.url : String(input || '')
  if (!raw.startsWith(apiBase)) return null
  const url = new URL(raw)
  if (!url.searchParams.get('device_id')) url.searchParams.set('device_id', getDeviceId())
  return url.toString()
}

export function installDeviceSessionGuard() {
  if (installed || typeof window === 'undefined' || !window.fetch) return
  installed = true
  const originalFetch = window.fetch.bind(window)
  window.fetch = async (input, init) => {
    const nextUrl = apiUrlWithDevice(input)
    let nextInput = input
    if (nextUrl) {
      nextInput = input instanceof Request ? new Request(nextUrl, input) : nextUrl
    }
    const response = await originalFetch(nextInput, init)
    if (nextUrl && [409, 428].includes(response.status)) {
      const payload = await response.clone().json().catch(() => ({}))
      if (payload?.code === 'DEVICE_CONFLICT' || payload?.code === 'DEVICE_ID_REQUIRED') {
        window.dispatchEvent(new CustomEvent('vera-device-conflict', { detail: payload }))
      }
    }
    return response
  }
}

export async function claimCurrentDevice(session) {
  if (!apiBase || !session?.access_token) return null
  const params = new URLSearchParams({ device_id: getDeviceId() })
  const response = await fetch(`${apiBase}/v2/device/claim?${params}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${session.access_token}`,
      'Content-Type': 'application/json',
    },
  })
  const payload = await response.json().catch(() => ({}))

  // Frontend and Cloud Run are deployed independently. During a rolling
  // deployment the browser can receive this login flow before the backend has
  // /v2/device/claim. Do not turn a valid username/password into a forced
  // logout just because the optional claim route is not live yet. Once the
  // backend guard is deployed, the claim succeeds and still replaces the old
  // device as designed.
  if ([404, 405].includes(response.status)) {
    return { ok: true, rollout_pending: true }
  }

  if (!response.ok) throw new Error(payload.detail || payload.message || `HTTP ${response.status}`)
  return payload
}
