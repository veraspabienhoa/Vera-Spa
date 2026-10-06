import { useEffect, useRef } from 'react'

// Listen directly so an accepted horizontal drag can prevent native scrolling
// on iOS. Vertical gestures and horizontal tables outside the edge stay native.
export default function useMenuWipe(shellRef, open, onOpenChange) {
  const latest = useRef({ open, onOpenChange })
  latest.current = { open, onOpenChange }
  useEffect(() => {
    const shell = shellRef.current
    if (!shell) return undefined
    let gesture = null
    let suppressClickUntil = 0
    const clear = () => {
      gesture = null
      shell.classList.remove('menu-dragging')
      shell.style.removeProperty('--menu-offset')
    }
    const start = event => {
      if (!window.matchMedia('(max-width: 820px)').matches || event.touches.length !== 1) return
      if (event.target.closest?.('input,textarea,select,[contenteditable="true"],dialog,[role="dialog"]')) return
      const touch = event.touches[0]
      if (!latest.current.open && touch.clientX > 48) return
      const width = shell.querySelector('.sidebar')?.getBoundingClientRect().width
      if (!width) return
      gesture = { id: touch.identifier, x: touch.clientX, y: touch.clientY, width,
        initiallyOpen: latest.current.open, offset: latest.current.open ? width : 0, dragging: false }
    }
    const move = event => {
      if (!gesture) return
      if (event.touches.length !== 1) { clear(); return }
      const touch = [...event.touches].find(item => item.identifier === gesture.id)
      if (!touch) return
      const dx = touch.clientX - gesture.x, dy = touch.clientY - gesture.y
      if (!gesture.dragging) {
        if (Math.max(Math.abs(dx), Math.abs(dy)) < 8) return
        if (Math.abs(dy) >= Math.abs(dx) || (!gesture.initiallyOpen && dx < 0)) { clear(); return }
        gesture.dragging = true
        shell.classList.add('menu-dragging')
      }
      event.preventDefault()
      gesture.offset = Math.max(0, Math.min(gesture.width, (gesture.initiallyOpen ? gesture.width : 0) + dx))
      shell.style.setProperty('--menu-offset', `${gesture.offset}px`)
    }
    const end = () => {
      if (!gesture) return
      if (gesture.dragging) {
        suppressClickUntil = Date.now() + 350
        const threshold = gesture.initiallyOpen ? .7 : .3
        latest.current.onOpenChange(gesture.offset >= gesture.width * threshold)
      }
      clear()
    }
    const cancel = () => { if (gesture?.dragging) suppressClickUntil = Date.now() + 350; clear() }
    const click = event => {
      if (Date.now() < suppressClickUntil) { event.preventDefault(); event.stopPropagation() }
    }
    shell.addEventListener('touchstart', start, { passive: true })
    shell.addEventListener('touchmove', move, { passive: false })
    shell.addEventListener('touchend', end)
    shell.addEventListener('touchcancel', cancel)
    shell.addEventListener('click', click, true)
    window.addEventListener('resize', cancel)
    return () => {
      shell.removeEventListener('touchstart', start)
      shell.removeEventListener('touchmove', move)
      shell.removeEventListener('touchend', end)
      shell.removeEventListener('touchcancel', cancel)
      shell.removeEventListener('click', click, true)
      window.removeEventListener('resize', cancel)
      clear()
    }
  }, [shellRef])
}
