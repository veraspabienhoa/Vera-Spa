import TrainingNoticeDetail from './TrainingNoticeDetail'
import UiCustomText from './UiCustomText'
import { useEffect, useRef, useState } from 'react'
import { BellRing, CheckCircle2, CircleAlert, Info, X } from 'lucide-react'
import { veraApi } from '../lib/api'
import { createVisiblePoller } from '../lib/visiblePoller'

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
  const [trainingDetail, setTrainingDetail] = useState(null)
  const settings = useRef({})
  const seen = useRef(new WeakMap())
  const recentMessages = useRef(new Map())
  const seenTraining = useRef(new Set())
  const seenRouted = useRef(new Set())
  useEffect(() => {
    let active = true
    const loadSettings = () => veraApi.notificationSettings().then((result) => {
      if (active) settings.current = Object.fromEntries((result.settings || []).map((item) => [item.key, item]))
    }).catch(() => {})
    const settingsPoller = createVisiblePoller(loadSettings, { interval: 60000 })
    const loadTrainingNotifications = () => veraApi.trainingNotifications('popup').then((result) => {
      if (!active) return
      if (settings.current.training_completed?.enabled === false || settings.current.training_completed?.channel_enabled?.popup === false) return
      const fresh = (result.notifications || []).filter(item => !item.is_read && !seenTraining.current.has(item.id))
      fresh.forEach(item => seenTraining.current.add(item.id))
      if (fresh.length) setItems(current => [...current, ...fresh.map(item => ({
        id: `training-${item.id}`, notificationId: item.id, message: `${item.title} · ${item.body}`,
        type: 'info', category: 'training_completed', persistent: true,
      }))].slice(-5))
    }).catch(() => {})
    const trainingPoller = createVisiblePoller(loadTrainingNotifications, { interval: 30000 })
    const loadRoutedPopups = () => veraApi.notificationPopup().then(result => {
      if (!active) return
      const fresh = (result.notifications || []).filter(item => !seenRouted.current.has(item.id))
      fresh.forEach(item => seenRouted.current.add(item.id))
      if (fresh.length) setItems(current => [...current, ...fresh.map(item => ({
        id: `route-${item.id}`, routeId: item.id, message: `${item.payload?.title || 'Thông báo'} · ${item.payload?.body || ''}`,
        type:'info', category:'routed_popup', persistent:true,
      }))].slice(-10))
    }).catch(() => {})
    const routedPoller = createVisiblePoller(loadRoutedPopups, { interval: 30000 })
    const onSettingsChanged = (event) => {
      const item = event?.detail
      if (item?.key) settings.current = { ...settings.current, [item.key]: item }
      else void settingsPoller.refresh()
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
      if (settings.current[category]?.enabled === false || settings.current[category]?.channel_enabled?.popup === false) return
      if (settings.current[category]?.has_rules) void veraApi.routeLocalNotification(category).catch(()=>{})
      if (settings.current[category]?.routed) return
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
      trainingPoller.stop()
      routedPoller.stop()
      settingsPoller.stop()
      observer.disconnect()
      window.removeEventListener('vera-notification-settings-changed', onSettingsChanged)
    }
  }, [])
  const openTrainingDetail = async (item) => {
    if (!item.notificationId) return
    try {
      setTrainingDetail(await veraApi.trainingNotificationDetail(item.notificationId))
      setItems(current => current.filter(row => row.id !== item.id))
    } catch { /* notification may have been removed */ }
  }
  const dismiss = item => {
    setItems(current => current.filter(row => row.id !== item.id))
    if (item.routeId) void veraApi.readNotification(item.routeId).catch(() => {})
  }
  if (!items.length && !trainingDetail) return null
  return <>
    {!!items.length && <div className="popup-notification-stack" aria-label="Thông báo trên màn hình">{items.map(item => <div key={item.id} className={`popup-notification ${item.type}`} role="status">
      {item.notificationId ? <BellRing size={19}/> : item.type === 'success' ? <CheckCircle2 size={19}/> : item.type === 'error' ? <CircleAlert size={19}/> : <Info size={19}/>} {item.notificationId ? <button data-ui-key="u-0455df928cb2" type="button" className="popup-notification-open" onClick={() => openTrainingDetail(item)}>{item.message}<small>Bấm để xem chi tiết</small></button> : <span>{item.message}</span>}<button data-ui-key="u-733434ac2d70" type="button" aria-label="Đóng thông báo" onClick={() => dismiss(item)}><X size={16}/></button>
    </div>)}</div>}
    {trainingDetail && <TrainingNoticeDetail notice={trainingDetail} onClose={() => setTrainingDetail(null)} />}
  </>
}
