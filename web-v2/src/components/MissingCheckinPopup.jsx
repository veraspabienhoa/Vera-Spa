import { useEffect, useId, useRef, useState } from 'react'
import { BellRing, X } from 'lucide-react'
import { subscribeNotificationFeed } from '../lib/notificationFeed'
import { createVisiblePoller } from '../lib/visiblePoller'
import './MissingCheckinPopup.css'

import { canSeeMissingCheckins } from '../lib/missingCheckinAudience'
const keyOf = row => row.tag || row.key
const savedKeys = storageKey => {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '[]')
    return new Set(Array.isArray(saved) ? saved.filter(key => typeof key === 'string').slice(-200) : [])
  } catch { return new Set() }
}

export default function MissingCheckinPopup({ user }) {
  const [alerts, setAlerts] = useState([])
  const [collapsed, setCollapsed] = useState(false)
  const contentId = useId()
  const dismissed = useRef(new Set())
  const role = user?.role, username = user?.username || user?.employee_username || user?.id
  const locked = Boolean(user?.must_change_password)
  const storageKey = `vera-missing-checkin-seen:${username || ''}`
  const collapseKey = `vera-missing-checkin-hidden:${username || ''}`
  useEffect(() => {
    dismissed.current = savedKeys(storageKey); setAlerts([])
    try { setCollapsed(localStorage.getItem(collapseKey) === 'true') } catch { setCollapsed(false) }
    if (!username || locked || !canSeeMissingCheckins(role)) return undefined
    const valid = row => keyOf(row) && Date.parse(row.expires_at) > Date.now()
    const unsubscribe = subscribeNotificationFeed(result => {
      const config = (result.settings || []).find(item => item.key === 'missing_checkin')
      const rows = config?.enabled === false || config?.channel_enabled?.popup === false ? [] : (result.missing_checkins || []).filter(valid)
      const unique = new Map(rows.map(row => [keyOf(row), row]))
      setAlerts([...unique.values()].filter(row => !dismissed.current.has(keyOf(row))))
    })
    // Expire the last successful snapshot even if later feed requests fail.
    const clock = createVisiblePoller(() => setAlerts(rows => rows.filter(valid)), { interval: 30_000 })
    const settingsChanged = event => {
      if (event.detail?.key === 'missing_checkin' && (event.detail.enabled === false || event.detail.channel_enabled?.popup === false)) setAlerts([])
    }
    const seenChanged = event => {
      if (event.key === collapseKey) { setCollapsed(event.newValue === 'true'); return }
      if (event.key !== storageKey) return
      dismissed.current = savedKeys(storageKey)
      setAlerts(rows => rows.filter(row => !dismissed.current.has(keyOf(row))))
    }
    window.addEventListener('storage', seenChanged)
    window.addEventListener('vera-notification-settings-changed', settingsChanged)
    return () => { unsubscribe(); clock.stop(); window.removeEventListener('storage', seenChanged); window.removeEventListener('vera-notification-settings-changed', settingsChanged) }
  }, [role, username, locked, storageKey, collapseKey])
  const dismissRows = rows => {
    const keys = new Set(rows.map(keyOf))
    dismissed.current = new Set([...savedKeys(storageKey), ...dismissed.current, ...keys].slice(-200))
    try { localStorage.setItem(storageKey, JSON.stringify([...dismissed.current])) } catch { /* Keep dismissal in memory if storage is unavailable. */ }
    setAlerts(current => current.filter(item => !keys.has(keyOf(item))))
  }
  const toggle = () => {
    const next = !collapsed
    setCollapsed(next)
    try { localStorage.setItem(collapseKey, String(next)) } catch { /* Keep the current display choice in memory. */ }
  }
  if (!username || locked || !canSeeMissingCheckins(role) || !alerts.length) return null
  return <section className="missing-checkin-popup" role="region" aria-label="Nhân viên chưa check-in" aria-live="polite">
    <header><BellRing size={18}/><strong>Chưa có check-in · {alerts.length}</strong><button type="button" aria-expanded={!collapsed} aria-controls={contentId} onClick={toggle}>{collapsed ? 'Hiện thông báo' : 'Ẩn thông báo'}</button><button type="button" className="missing-checkin-close" aria-label="Đóng popup chưa check-in" title="Đóng popup" onClick={() => dismissRows(alerts)}><X size={20} aria-hidden="true"/></button></header>
    <div id={contentId} hidden={collapsed}>
      <p>Có lịch làm, quá giờ vào ca 15 phút và chưa có lịch nghỉ.</p>
      <ul>{alerts.map(row => <li key={keyOf(row)}><strong>{row.employee}</strong><span>{row.body}</span><button type="button" className="missing-checkin-seen" aria-label={`Đã xem thông báo của ${row.employee}`} onClick={() => dismissRows([row])}>Đã xem</button></li>)}</ul>
    </div>
  </section>
}
