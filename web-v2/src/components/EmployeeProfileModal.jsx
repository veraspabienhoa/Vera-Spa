import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'
import './EmployeeProfileModal.css'

export default function EmployeeProfileModal({ children, onClose, busy }) {
  const root = useRef(null)
  const actions = useRef({ onClose, busy })
  actions.current = { onClose, busy }

  useEffect(() => {
    const opener = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    root.current?.focus()
    const onKeyDown = (event) => {
      // Nested calendars and image viewers handle their own keyboard events.
      if (event.defaultPrevented || !root.current?.contains(event.target)) return
      if (event.key === 'Escape' && !actions.current.busy) {
        event.preventDefault()
        actions.current.onClose()
      }
      if (event.key !== 'Tab') return
      const controls = Array.from(root.current.querySelectorAll(
        'button, input, select, textarea, a[href], [tabindex="0"]',
      )).filter((node) => !node.disabled && node.tabIndex >= 0 && node.getClientRects().length)
      const first = controls[0]
      const last = controls.at(-1)
      if (!first) { event.preventDefault(); return }
      if (event.shiftKey && (event.target === first || event.target === root.current)) {
        event.preventDefault(); last.focus()
      } else if (!event.shiftKey && (event.target === last || event.target === root.current)) {
        event.preventDefault(); first.focus()
      }
    }
    document.addEventListener('keydown', onKeyDown)
    return () => {
      document.removeEventListener('keydown', onKeyDown)
      document.body.style.overflow = overflow
      if (opener?.isConnected) opener.focus({ preventScroll: true })
    }
  }, [])

  return createPortal(
    <div className="employee-profile-modal-backdrop">
      <div className="employee-profile-modal" ref={root} role="dialog" aria-modal="true"
        aria-labelledby="employee-profile-modal-title" tabIndex={-1}>
        {children}
      </div>
    </div>, document.body,
  )
}
