import { useEffect, useLayoutEffect, useRef } from 'react'

import { restoreFilterAnchor } from './filterScrollAnchor'

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
