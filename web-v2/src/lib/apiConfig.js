// Login, refresh, profile verification and business reads must use one backend.
// Keep staging/local overrides, and use the canonical production API when the
// build variable is absent or blank. Never fall back to a second auth provider.
export const apiBase = (import.meta.env.VITE_VERA_API_BASE_URL?.trim() || 'https://api.veraspa.vn').replace(/\/+$/, '')
