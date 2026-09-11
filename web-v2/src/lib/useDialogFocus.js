import { useEffect, useRef } from 'react'

export default function useDialogFocus(onClose) {
  const dialogRef = useRef(null)
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useEffect(() => {
    const previous = document.activeElement
    const dialog = dialogRef.current
    const targets = () => [...(dialog?.querySelectorAll('button:not([disabled]),input:not([disabled]),select:not([disabled]),textarea:not([disabled]),[tabindex="0"]') || [])]
    const frame = window.requestAnimationFrame(() => (targets()[0] || dialog)?.focus({ preventScroll: true }))
    const keydown = (event) => {
      if (event.key === 'Escape') { event.preventDefault(); closeRef.current?.(); return }
      if (event.key !== 'Tab') return
      const items = targets(), first = items[0], last = items[items.length - 1]
      if (!first) { event.preventDefault(); dialog?.focus(); return }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus() }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus() }
    }
    document.addEventListener('keydown', keydown)
    return () => { window.cancelAnimationFrame(frame); document.removeEventListener('keydown', keydown); previous?.focus?.({ preventScroll: true }) }
  }, [])
  return dialogRef
}
