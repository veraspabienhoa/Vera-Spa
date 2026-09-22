import { useEffect, useRef } from 'react'
import { createPortal } from 'react-dom'

export default function NotificationEditorDialog({ children, title, busy, onClose }) {
  const dialog = useRef(null)
  const state = useRef({ busy, onClose })
  state.current = { busy, onClose }
  useEffect(() => {
    const node = dialog.current, opener = document.activeElement
    const overflow = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    if (node.showModal) node.showModal()
    else node.setAttribute('open', '')
    const initialFocus = node.querySelector('input:not([type=checkbox]):not([disabled])') || node.querySelector('button:not([disabled])')
    initialFocus?.focus()
    const cancel = event => { event.preventDefault(); if (!state.current.busy) state.current.onClose() }
    node.addEventListener('cancel', cancel)
    return () => {
      node.removeEventListener('cancel', cancel)
      if (node.close) node.close()
      document.body.style.overflow = overflow
      if (opener?.isConnected) opener.focus()
    }
  }, [])
  return createPortal(<dialog ref={dialog} role="dialog" aria-modal="true" aria-labelledby="notification-dialog-title" className="notification-settings-page notification-modal">
    <header className="notification-modal-head"><h3 id="notification-dialog-title">{title}</h3><button type="button" disabled={busy} onClick={onClose} aria-label="Đóng hộp thoại thông báo">✕</button></header>
    <div className="notification-editor">{children}</div>
  </dialog>, document.body)
}
