// Keep the filter being edited at the same viewport position when sections
// above it resize. Reserve only enough space for the viewport, not old rows.
export function restoreFilterAnchor(anchor, snapshot, viewport = window) {
  const panel = anchor?.closest('section')
  if (!panel || !snapshot) return
  const offset = anchor.getBoundingClientRect().top - panel.getBoundingClientRect().top
  panel.style.minHeight = `${Math.max(0, viewport.innerHeight - snapshot.top + offset)}px`
  const delta = anchor.getBoundingClientRect().top - snapshot.top
  if (Math.abs(delta) > 1) viewport.scrollBy({ top: delta, behavior: 'instant' })
}

