import NotificationModal from './NotificationModal'
import { useEffect, useId, useRef, useState } from 'react'
import { BellRing, X } from 'lucide-react'
import { subscribeNotificationFeed } from '../lib/notificationFeed'
import { createVisiblePoller } from '../lib/visiblePoller'
import './MissingCheckinPopup.css'

import { canSeeMissingCheckins } from '../lib/missingCheckinAudience'
const keyOf = row => row.tag || row.key
const REMIND_AFTER_MS = 15 * 60 * 1000
const savedKeys = storageKey => {
  try {
    const saved = JSON.parse(localStorage.getItem(storageKey) || '[]')
    // Old permanent acknowledgements have no timestamp: let the next fresh
    // feed verify whether these employees still need a reminder.
    return new Map(Array.isArray(saved) ? saved.filter(entry => Array.isArray(entry)
      && typeof entry[0] === 'string' && Number.isFinite(entry[1])
      && entry[1] > Date.now()).slice(-200) : [])
  } catch { return new Map() }
}
const snoozed = (entries, key) => (entries.get(key) || 0) > Date.now()

export default function MissingCheckinPopup({ user }) {
  const [alerts, setAlerts] = useState([])
  const [collapsed, setCollapsed] = useState(false)
  const contentId = useId()
  const dismissed = useRef(new Map())
  const visibleKeys = useRef(new Set())
  const role = user?.role, username = user?.username || user?.employee_username || user?.id
  const locked = Boolean(user?.must_change_password)
  const storageKey = `vera-missing-checkin-seen:${username || ''}`
  useEffect(() => {
    dismissed.current = savedKeys(storageKey); setAlerts([])
    setCollapsed(false)
    visibleKeys.current = new Set()
    if (!username || locked || !canSeeMissingCheckins(role)) return undefined
    const valid = row => keyOf(row) && Date.parse(row.expires_at) > Date.now()
    const unsubscribe = subscribeNotificationFeed(result => {
      const config = (result.settings || []).find(item => item.key === 'missing_checkin')
      const rows = config?.enabled === false || config?.channel_enabled?.popup === false ? [] : (result.missing_checkins || []).filter(valid)
      const unique = new Map(rows.map(row => [keyOf(row), row]))
      const next = [...unique.values()].filter(row => !snoozed(dismissed.current, keyOf(row)))
      if (next.some(row => !visibleKeys.current.has(keyOf(row)))) setCollapsed(false)
      visibleKeys.current = new Set(next.map(keyOf))
      setAlerts(next)
    })
    // Expire the last successful snapshot even if later feed requests fail.
    const clock = createVisiblePoller(() => setAlerts(rows => rows.filter(valid)), { interval: 30_000 })
    const settingsChanged = event => {
      if (event.detail?.key === 'missing_checkin' && (event.detail.enabled === false || event.detail.channel_enabled?.popup === false)) setAlerts([])
    }
    const seenChanged = event => {
      if (event.key !== storageKey) return
      dismissed.current = savedKeys(storageKey)
      setAlerts(rows => rows.filter(row => !snoozed(dismissed.current, keyOf(row))))
    }
    window.addEventListener('storage', seenChanged)
    window.addEventListener('vera-notification-settings-changed', settingsChanged)
    return () => { unsubscribe(); clock.stop(); window.removeEventListener('storage', seenChanged); window.removeEventListener('vera-notification-settings-changed', settingsChanged) }
  }, [role, username, locked, storageKey])
  const dismissRows = rows => {
    const keys = new Set(rows.map(keyOf))
    visibleKeys.current = new Set([...visibleKeys.current].filter(key => !keys.has(key)))
    const until = Date.now() + REMIND_AFTER_MS
    dismissed.current = new Map([...savedKeys(storageKey), ...dismissed.current,
      ...[...keys].map(key => [key, until])].filter(([, expiry]) => expiry > Date.now()).slice(-200))
    try { localStorage.setItem(storageKey, JSON.stringify([...dismissed.current])) } catch { /* Keep dismissal in memory if storage is unavailable. */ }
    setAlerts(current => current.filter(item => !keys.has(keyOf(item))))
  }
  const toggle = () => {
    setCollapsed(current => !current)
  }
  if (!username || locked || !canSeeMissingCheckins(role) || !alerts.length) return null
  return <NotificationModal title="Nhân viên chưa check-in" onClose={() => dismissRows(alerts)}><section className="missing-checkin-popup" role="region" aria-label="Nhân viên chưa check-in" aria-live="polite">
    <header><BellRing size={18}/><strong>Chưa có check-in · {alerts.length}</strong><button type="button" aria-expanded={!collapsed} aria-controls={contentId} onClick={toggle}>{collapsed ? 'Hiện thông báo' : 'Ẩn thông báo'}</button><button data-dialog-close="true" type="button" className="missing-checkin-close" aria-label="Đóng popup chưa check-in" title="Đóng popup" onClick={() => dismissRows(alerts)}><X size={20} aria-hidden="true"/></button></header>
    <div id={contentId} hidden={collapsed}>
      <p>Có lịch làm, quá giờ vào ca 15 phút và chưa có lịch nghỉ.</p>
      <ul>{alerts.map(row => <li key={keyOf(row)}><strong>{row.employee}</strong><span>{row.body}</span><button type="button" className="missing-checkin-seen" aria-label={`Đã xem thông báo của ${row.employee}`} onClick={() => dismissRows([row])}>Đã xem</button></li>)}</ul>
    </div>
  </section></NotificationModal>
}
