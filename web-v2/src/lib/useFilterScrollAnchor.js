import { useEffect, useLayoutEffect, useRef } from 'react'

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

export default function useFilterScrollAnchor() {
  const ref = useRef(null)
  const position = useRef(null)
  const capture = () => {
    const top = ref.current?.getBoundingClientRect().top
    if (top != null && top >= 0 && top < window.innerHeight) {
      position.current = { top }
      restoreFilterAnchor(ref.current, position.current)
    }
  }
  useLayoutEffect(() => { restoreFilterAnchor(ref.current, position.current) })
  useEffect(() => {
    const cancel = () => { position.current = null }
    const pointer = event => { if (!ref.current?.contains(event.target)) cancel() }
    const key = event => { if (['PageUp', 'PageDown', 'Home', 'End', 'ArrowUp', 'ArrowDown', ' '].includes(event.key) && !['INPUT', 'TEXTAREA', 'SELECT'].includes(event.target.tagName)) cancel() }
    window.addEventListener('wheel', cancel, { passive: true })
    window.addEventListener('touchmove', cancel, { passive: true })
    window.addEventListener('resize', cancel)
    document.addEventListener('pointerdown', pointer, true)
    document.addEventListener('keydown', key, true)
    return () => {
      window.removeEventListener('wheel', cancel)
      window.removeEventListener('touchmove', cancel)
      window.removeEventListener('resize', cancel)
      document.removeEventListener('pointerdown', pointer, true)
      document.removeEventListener('keydown', key, true)
    }
  }, [])
  return { ref, onClickCapture: capture, onChangeCapture: capture }
}
