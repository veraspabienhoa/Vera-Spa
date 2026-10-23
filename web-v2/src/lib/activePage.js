// Navigation belongs to this browser tab and verified account, never a shared
// server preference or localStorage value that another tab can overwrite.
const key = user => `vera-v2-tab-active-page:${user?.id}`
export function readActivePage(user, validPages, target = window) {
  if (!user?.id) return 'live-tour'
  try {
    const page = target.sessionStorage.getItem(key(user))
    return validPages.has(page) ? page : 'live-tour'
  } catch { return 'live-tour' }
}
export function rememberActivePage(user, page, validPages, target = window) {
  if (!user?.id || !validPages.has(page)) return
  try { target.sessionStorage.setItem(key(user), page) } catch { /* Private storage may be unavailable. */ }
}
export function forgetActivePage(user, target = window) {
  if (!user?.id) return
  try { target.sessionStorage.removeItem(key(user)) } catch { /* Ignore unavailable storage. */ }
}
