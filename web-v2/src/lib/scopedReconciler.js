// Compatibility helpers run only when their own UI changes, with no idle timer.
export function startScopedReconciler(selector, reconcile, attributes = []) {
  const roots = new Map()
  let frame = null
  const schedule = () => {
    if (frame !== null || document.hidden || !roots.size) return
    frame = window.requestAnimationFrame(() => {
      frame = null
      reconcile()
      // Ignore synchronous compatibility edits made by this reconciliation.
      roots.forEach(observer => observer.takeRecords())
    })
  }
  const discover = node => {
    if (!(node instanceof Element)) return
    const candidates = [...(node.matches(selector) ? [node] : []), ...node.querySelectorAll(selector)]
    for (const root of candidates) {
      if (roots.has(root)) continue
      const observer = new MutationObserver(schedule)
      observer.observe(root, { childList: true, subtree: true,
        ...(attributes.length ? { attributes: true, attributeFilter: attributes } : {}) })
      roots.set(root, observer)
      schedule()
    }
  }
  const discovery = new MutationObserver(records => {
    for (const [root, observer] of roots) {
      if (!root.isConnected) { observer.disconnect(); roots.delete(root) }
    }
    for (const record of records) {
      if ([...roots.keys()].some(root => root.contains(record.target))) continue
      record.addedNodes.forEach(discover)
    }
  })
  discover(document.body)
  discovery.observe(document.body, { childList: true, subtree: true })
  const interaction = event => { if (event.target?.closest?.(selector)) schedule() }
  for (const name of ['click', 'input', 'change']) document.addEventListener(name, interaction, true)
  document.addEventListener('visibilitychange', schedule)
  return () => {
    discovery.disconnect()
    roots.forEach(observer => observer.disconnect()); roots.clear()
    if (frame !== null) window.cancelAnimationFrame(frame)
    for (const name of ['click', 'input', 'change']) document.removeEventListener(name, interaction, true)
    document.removeEventListener('visibilitychange', schedule)
  }
}
