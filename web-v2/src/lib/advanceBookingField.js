// Focus during the selection gesture so mobile Safari keeps keyboard access.
export function advanceBookingField(current) {
  if (!current || current.getAttribute('aria-invalid') === 'true') return
  const fields = [...(current.closest('form')?.querySelectorAll('[data-booking-step]') || [])]
  const next = fields.slice(fields.indexOf(current) + 1).find(field => !field.matches(':disabled') && !field.hidden)
  if (!next) return
  next.focus({ preventScroll: true })
  next.scrollIntoView?.({ block: 'nearest', inline: 'nearest' })
  if (next.tagName === 'SELECT') {
    try { next.showPicker?.() } catch { /* Some mobile browsers only support focus. */ }
  }
}
