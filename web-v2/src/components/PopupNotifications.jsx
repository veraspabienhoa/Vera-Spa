import { useEffect, useRef, useState } from 'react'
import { CheckCircle2, CircleAlert, Info, X } from 'lucide-react'
import { veraApi } from '../lib/api'

const SELECTOR = '[role="alert"],.error-box,.success-box,.warning-box,.setup-note'
const GUIDANCE_PATTERN = /(?:hãy|vui lòng|chưa chọn|chọn .*nhân viên|bộ lọc|lọc|tìm kiếm|không tìm thấy .*phù hợp)/i

const categoryFor = (type, message) => {
  if (GUIDANCE_PATTERN.test(message)) return 'ui_guidance'
  if (type === 'success') return 'ui_success'
  if (type === 'warning') return 'ui_warning'
  return 'ui_error'
}

export default function PopupNotifications() {
  const [items, setItems] = useState([])
  const settings = useRef({})
  const seen = useRef(new WeakMap())
  const recentMessages = useRef(new Map())
  useEffect(() => {
    let active = true
    const loadSettings = () => veraApi.notificationSettings().then((result) => {
      if (active) settings.current = Object.fromEntries((result.settings || []).map((item) => [item.key, item.enabled]))
    }).catch(() => {})
    void loadSettings()
    const onSettingsChanged = (event) => {
      const item = event?.detail
      if (item?.key) settings.current = { ...settings.current, [item.key]: item.enabled }
      else void loadSettings()
    }
    window.addEventListener('vera-notification-settings-changed', onSettingsChanged)
    const add = element => {
      if (!(element instanceof HTMLElement) || element.closest('.popup-notification-stack')) return
      const message = String(element.textContent || '').replace(/\s+/g, ' ').trim()
      if (!message || seen.current.get(element) === message) return
      seen.current.set(element, message)
      const type = element.classList.contains('success-box') ? 'success'
        : element.classList.contains('warning-box') || element.classList.contains('setup-note') ? 'warning' : 'error'
      const category = categoryFor(type, message)
      if (settings.current[category] === false) return
      const duplicateKey = `${category}:${message.toLocaleLowerCase('vi-VN')}`
      const now = Date.now()
      if (now - Number(recentMessages.current.get(duplicateKey) || 0) < 15000) return
      recentMessages.current.set(duplicateKey, now)
      for (const [key, timestamp] of recentMessages.current) {
        if (now - timestamp > 60000) recentMessages.current.delete(key)
      }
      const id = `${Date.now()}-${Math.random()}`
      setItems(current => [...current.slice(-2), { id, message, type, category }])
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
    return () => {
      active = false
      observer.disconnect()
      window.removeEventListener('vera-notification-settings-changed', onSettingsChanged)
    }
  }, [])
  if (!items.length) return null
  return <div className="popup-notification-stack" aria-label="Thông báo trên màn hình">{items.map(item => <div key={item.id} className={`popup-notification ${item.type}`} role="status">
    {item.type === 'success' ? <CheckCircle2 size={19}/> : item.type === 'error' ? <CircleAlert size={19}/> : <Info size={19}/>}
    <span>{item.message}</span><button type="button" aria-label="Đóng thông báo" onClick={() => setItems(current => current.filter(row => row.id !== item.id))}><X size={16}/></button>
  </div>)}</div>
}
