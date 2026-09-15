import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, CircleAlert, Info, X } from 'lucide-react'

const SELECTOR = '[role="alert"],.error-box,.success-box,.warning-box,.setup-note'

export default function PopupNotifications() {
  const [items, setItems] = useState([])
  const seen = useRef(new WeakMap())
  useEffect(() => {
    const add = element => {
      if (!(element instanceof HTMLElement) || element.closest('.popup-notification-stack')) return
      const message = String(element.textContent || '').replace(/\s+/g, ' ').trim()
      if (!message || seen.current.get(element) === message) return
      seen.current.set(element, message)
      const type = element.classList.contains('success-box') ? 'success'
        : element.classList.contains('warning-box') || element.classList.contains('setup-note') ? 'warning' : 'error'
      const id = `${Date.now()}-${Math.random()}`
      setItems(current => [...current.slice(-3), { id, message, type }])
      window.setTimeout(() => setItems(current => current.filter(item => item.id !== id)), type === 'error' ? 10000 : 6500)
    }
    const observer = new MutationObserver(mutations => mutations.forEach(mutation => {
      const target = mutation.target instanceof HTMLElement ? mutation.target.closest(SELECTOR) : null
      if (target) add(target)
      mutation.addedNodes.forEach(node => {
        if (!(node instanceof HTMLElement)) return
        if (node.matches(SELECTOR)) add(node)
        node.querySelectorAll(SELECTOR).forEach(add)
      })
    }))
    observer.observe(document.body, { childList: true, subtree: true, characterData: true })
    return () => observer.disconnect()
  }, [])
  if (!items.length) return null
  return <div className="popup-notification-stack" aria-label="Thông báo trên màn hình">{items.map(item => <div key={item.id} className={`popup-notification ${item.type}`} role="status">
    {item.type === 'success' ? <CheckCircle2 size={19}/> : item.type === 'error' ? <CircleAlert size={19}/> : <Info size={19}/>}
    <span>{item.message}</span><button type="button" aria-label="Đóng thông báo" onClick={() => setItems(current => current.filter(row => row.id !== item.id))}><X size={16}/></button>
  </div>)}</div>
}
