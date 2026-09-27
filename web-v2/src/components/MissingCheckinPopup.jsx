import { useEffect, useRef, useState } from 'react'
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
  const dismissed = useRef(new Set())
  const role = user?.role, username = user?.username || user?.employee_username || user?.id
  const locked = Boolean(user?.must_change_password)
  const storageKey = `vera-missing-checkin-seen:${username || ''}`
  useEffect(() => {
    dismissed.current = savedKeys(storageKey); setAlerts([])
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
      if (event.key !== storageKey) return
      dismissed.current = savedKeys(storageKey)
      setAlerts(rows => rows.filter(row => !dismissed.current.has(keyOf(row))))
    }
    window.addEventListener('storage', seenChanged)
    window.addEventListener('vera-notification-settings-changed', settingsChanged)
    return () => { unsubscribe(); clock.stop(); window.removeEventListener('storage', seenChanged); window.removeEventListener('vera-notification-settings-changed', settingsChanged) }
  }, [role, username, locked, storageKey])
  const markSeen = () => {
    dismissed.current = new Set([...savedKeys(storageKey), ...dismissed.current, ...alerts.map(keyOf)].slice(-200))
    try { localStorage.setItem(storageKey, JSON.stringify([...dismissed.current])) } catch { /* Keep dismissal in memory if storage is unavailable. */ }
    setAlerts([])
  }
  if (!username || locked || !canSeeMissingCheckins(role) || !alerts.length) return null
  return <section className="missing-checkin-popup" role="region" aria-label="Nhân viên chưa check-in" aria-live="polite">
    <header><BellRing size={18}/><strong>Chưa có check-in · {alerts.length}</strong><button type="button" aria-label="Ẩn cảnh báo chưa check-in" onClick={markSeen}><X size={18}/></button></header>
    <p>Có lịch làm, quá giờ vào ca 15 phút và chưa có lịch nghỉ.</p>
    <ul>{alerts.map(row => <li key={keyOf(row)}><strong>{row.employee}</strong><span>{row.body}</span></li>)}</ul>
    <button type="button" className="missing-checkin-seen" onClick={markSeen}>Đã xem</button>
  </section>
}
