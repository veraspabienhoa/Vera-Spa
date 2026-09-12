const eventName = 'vera:leave-updated'

export function notifyLeaveChange(result) {
  window.dispatchEvent(new Event(eventName))
  try { window.localStorage.setItem(eventName, `${Date.now()}:${Math.random()}`) } catch { /* Polling remains available. */ }
  return result
}

export function watchLeaveChanges(refresh) {
  const storage = (event) => { if (event.key === eventName) refresh() }
  window.addEventListener(eventName, refresh)
  window.addEventListener('storage', storage)
  return () => {
    window.removeEventListener(eventName, refresh)
    window.removeEventListener('storage', storage)
  }
}
