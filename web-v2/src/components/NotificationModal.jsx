import { useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { showSystemDialog } from '../lib/systemDialogs'

// Portal content stays live while queued (timers, counts and action permissions).
export default function NotificationModal({ title = 'Thông báo', onClose, children }) {
  const [content] = useState(() => document.createElement('div'))
  const closeRef = useRef(onClose)
  closeRef.current = onClose
  useLayoutEffect(() => {
    content.className = 'system-notification-content'
    const notice = showSystemDialog({ title, content, onDismiss: () => closeRef.current?.() })
    return () => notice.close()
  }, [content, title])
  return createPortal(children, content)
}
