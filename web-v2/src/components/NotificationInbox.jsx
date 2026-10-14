import StableFeedback from './StableFeedback'
import { useEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { veraApi } from '../lib/api'
import { subscribeNotificationFeed, refreshNotificationFeed } from '../lib/notificationFeed'
import { notificationPage } from '../lib/notificationNavigation'
import { formatVeraDateTime } from '../lib/veraDate'
import { Bell, Check, X } from 'lucide-react'
import './NotificationInbox.css'
const requested = () => { const id = new URLSearchParams(window.location.search).get('notification') || ''; return /^[1-9][0-9]{0,18}$/.test(id) ? id : '' }
const cleanTitle = title => String(title || 'Thông báo').replace(/^VERA SPA(?:\s*[·:–-]\s*|\s+)/i, '') || 'Thông báo'
const clearRequested = () => {
  const url = new URL(window.location.href)
  url.searchParams.delete('notification')
  window.history.replaceState(window.history.state, '', url)
}
export default function NotificationInbox({ showTrigger = true, user, onPageChange }) {
  const [items, setItems] = useState([]), [open, setOpen] = useState(() => Boolean(requested()))
  const [selected, setSelected] = useState(requested), [detail, setDetail] = useState(null)
  const [error, setError] = useState(''), [retry, setRetry] = useState(0)
  const [marking, setMarking] = useState(() => new Set())
  const pendingReads = useRef(new Set())
  const lifecycle = useRef(0)
  const selectedRef = useRef(selected)
  selectedRef.current = selected
  const dialog = useRef(null)
  const navigationTaken = useRef(false)
  const navigation = useRef({ user, onPageChange })
  navigation.current = { user, onPageChange }
  useEffect(() => {
    lifecycle.current += 1
    return () => { lifecycle.current += 1 }
  }, [])
  useEffect(() => {
    const openRequested = () => {
      const id = requested()
      if (!id) return
      navigationTaken.current = false
      setDetail(null); setError(''); setSelected(id); setOpen(true)
      setRetry(value => value + 1)
    }
    const onMessage = event => {
      if (event.data?.type !== 'vera-notification-open') return
      let target
      try { target = new URL(event.data.url, window.location.origin) } catch { return }
      if (target.origin !== window.location.origin) return
      const id = target.searchParams.get('notification') || ''
      if (!/^[1-9][0-9]{0,18}$/.test(id)) return
      const url = new URL(window.location.href)
      url.searchParams.set('notification', id)
      window.history.replaceState(window.history.state, '', url)
      openRequested()
    }
    navigator.serviceWorker?.addEventListener('message', onMessage)
    window.addEventListener('popstate', openRequested)
    return () => {
      navigator.serviceWorker?.removeEventListener('message', onMessage)
      window.removeEventListener('popstate', openRequested)
    }
  }, [])
  useEffect(() => {
    if (!showTrigger) return undefined
    return subscribeNotificationFeed(data => setItems(data.inbox || []))
  }, [showTrigger])
  useEffect(() => { if (open && dialog.current && !dialog.current.open) dialog.current.showModal() }, [open])
  useEffect(() => {
    if (!selected) return undefined
    let active = true
    veraApi.notificationDetail(selected).then(result => {
      if (!active) return
      const page = notificationPage(result, navigation.current.user)
      if (page && navigation.current.onPageChange && !navigationTaken.current) {
        navigationTaken.current = true
        setOpen(false); setSelected(''); setDetail(null); setError('')
        clearRequested()
        navigation.current.onPageChange(page)
        return
      }
      setDetail(result)
    }).catch(err => { if (active) setError(err.message || 'Không tải được chi tiết thông báo.') })
    return () => { active = false }
  }, [selected, retry])
  const close = () => {
    setOpen(false); setSelected(''); setDetail(null); setError('')
    clearRequested()
  }
  const openItem = item => {
    const page = notificationPage(item, user)
    if (page && onPageChange) {
      if (navigationTaken.current) return
      navigationTaken.current = true
      close()
      onPageChange(page)
      return
    }
    setDetail(null); setError(''); setSelected(String(item.id))
  }
  const markViewed = async id => {
    const key = String(id)
    if (pendingReads.current.has(key)) return
    pendingReads.current.add(key)
    const generation = lifecycle.current
    setMarking(new Set(pendingReads.current)); setError('')
    try {
      await veraApi.readNotification(id)
      if (generation !== lifecycle.current) return
      void refreshNotificationFeed()
      setItems(rows => rows.filter(row => String(row.id) !== String(id)))
      if (selectedRef.current === key) { setSelected(''); setDetail(null) }
    } catch (err) { if (generation === lifecycle.current) setError(err.message || 'Chưa đánh dấu được thông báo. Vui lòng thử lại.') }
    finally {
      pendingReads.current.delete(key)
      if (generation === lifecycle.current) setMarking(new Set(pendingReads.current))
    }
  }
  const unread = items.filter(item => !item.read_at).length
  return <section className="notification-inbox">
    {showTrigger && <button type="button" className="topbar-refresh-button topbar-open-tab-button notification-inbox-trigger" aria-label={unread ? `Thông báo hệ thống, ${unread} chưa đọc` : 'Thông báo hệ thống'} aria-expanded={open} onClick={() => { navigationTaken.current = false; setSelected(''); setError(''); setOpen(true) }}><Bell size={15}/><span>Thông báo hệ thống</span>{unread > 0 && <span className="notification-unread-dot" aria-hidden="true"/>}</button>}
    {open && createPortal(<dialog ref={dialog} className="notification-dialog" aria-labelledby="notification-heading" onCancel={close} onClick={event => { if (event.target === dialog.current) close() }}>
      <header><div className="notification-heading"><span className="notification-heading-icon"><Bell size={20}/></span><div><small>TRUNG TÂM THÔNG BÁO</small><h2 id="notification-heading">{selected ? 'Chi tiết thông báo' : 'Thông báo hệ thống'}</h2></div></div><button data-dialog-close="true" type="button" aria-label="Đóng thông báo" onClick={close}><X size={20}/></button></header>
      <div className="notification-dialog-content">
        <StableFeedback>{error && <div role="alert"><p>{error}</p>{selected && <button type="button" onClick={() => { setError(''); setRetry(n => n + 1) }}>Thử lại</button>}</div>}</StableFeedback>
        {selected ? detail ? <article className="notification-detail"><h3>{cleanTitle(detail.payload?.title)}</h3><p>{detail.payload?.body}</p><small>{formatVeraDateTime(detail.created_at)}</small>{showTrigger && <button type="button" className="notification-viewed" disabled={marking.size > 0} onClick={() => markViewed(detail.id)}><Check size={16}/> Đã xem</button>}</article> : !error && <p role="status">Đang tải chi tiết…</p> : <>
          {!items.length && <p>Chưa có thông báo.</p>}
          {items.map(item => <div className="notification-entry" key={item.id}><button type="button" className="notification-row unread" onClick={() => openItem(item)} title={`${cleanTitle(item.payload?.title)} — ${item.payload?.body || ''}`}><span className="notification-row-text"><strong>{cleanTitle(item.payload?.title)}</strong><span> — {item.payload?.body}</span></span><small>{formatVeraDateTime(item.created_at)}</small></button><button type="button" className="notification-viewed" disabled={marking.has(String(item.id))} onClick={() => markViewed(item.id)} aria-label={`Đã xem ${cleanTitle(item.payload?.title)}`}><Check size={15}/><span>Đã xem</span></button></div>)}
        </>}
      </div>
      {selected && showTrigger && <footer><button type="button" onClick={() => { setSelected(''); setDetail(null); setError('') }}>Về danh sách</button></footer>}
    </dialog>, document.body)}
  </section>
}
